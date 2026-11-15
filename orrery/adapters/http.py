"""
Governed HTTP/REST API Adapter (Law 2, Law 6).

Provides governed outbound HTTP communication over standard HTTPS/HTTP with:
- Defense-in-depth URL domain allowlisting (Law 2 Envelope)
- Cloud metadata service SSRF protection (169.254.169.254, metadata.google.internal)
- Fine-grained risk classification:
    GET, HEAD        -> ActionRisk.READ_ONLY
    POST, PUT, PATCH -> ActionRisk.COMPENSABLE
    DELETE           -> ActionRisk.IRREVERSIBLE (enforcing Approval Gate scrutiny)
- Response body truncation limits preventing memory exhaustion
- Signed execution receipts with response digests and latency metrics
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence, Union

from orrery.adapters.base import BaseAdapter
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

logger = logging.getLogger(__name__)

BLOCKED_SSRF_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "100.100.100.200",  # Alibaba Cloud metadata
    "fd00:ec2::254",    # IPv6 AWS IMDS
}


def _is_disallowed_ip(ip_str: str) -> bool:
    """Returns True for loopback, private, link-local, multicast, reserved, or unspecified IPs."""
    ip = ipaddress.ip_address(ip_str.split("%")[0])
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates every HTTP redirect hop against the SSRF and domain policy."""

    def __init__(self, validator):
        super().__init__()
        self._validator = validator

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        err = self._validator(newurl)
        if err:
            raise urllib.error.URLError(f"Redirect blocked by SSRF policy: {err}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpAdapter(BaseAdapter):
    """
    Adapter for governed REST API interactions.
    """

    adapter_name = "http"
    target_params: ClassVar[tuple] = ("url",)
    _redirect_handler_cls = _SafeRedirectHandler

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        "get": ActionRisk.READ_ONLY,
        "head": ActionRisk.READ_ONLY,
        "post": ActionRisk.COMPENSABLE,
        "put": ActionRisk.COMPENSABLE,
        "patch": ActionRisk.COMPENSABLE,
        "delete": ActionRisk.IRREVERSIBLE,
    }

    def __init__(
        self,
        allowed_domains: Optional[Sequence[str]] = None,
        blocked_hosts: Optional[Sequence[str]] = None,
        max_response_bytes: int = 5 * 1024 * 1024,
        default_timeout: float = 30.0,
        default_headers: Optional[Dict[str, str]] = None,
        is_simulation: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name=self.adapter_name, config=config)
        self.allowed_domains = set(d.lower() for d in allowed_domains) if allowed_domains else None
        self.blocked_hosts = set(h.lower() for h in (blocked_hosts or BLOCKED_SSRF_HOSTS))
        self.max_response_bytes = max_response_bytes
        self.default_timeout = default_timeout
        self.default_headers = default_headers or {}
        self.is_simulation = is_simulation

    def classify_risk(self, action: ActionPayload) -> ActionRisk:
        return self.risk_for(action.action_name)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "adapter": self.adapter_name,
            "allowed_domains": list(self.allowed_domains) if self.allowed_domains else "ALL",
            "blocked_hosts_count": len(self.blocked_hosts),
            "max_response_bytes": self.max_response_bytes,
            "is_simulation": self.is_simulation,
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        return await asyncio.to_thread(self.execute, action)

    def _validate_url(self, raw_url: str) -> Optional[str]:
        """Validates URL scheme, hostname, domain allowlist, and resolved IP addresses."""
        try:
            parsed = urllib.parse.urlparse(raw_url)
            if parsed.scheme not in ("http", "https"):
                return f"unsupported URL scheme '{parsed.scheme}': {raw_url}"
            hostname = (parsed.hostname or "").lower()
            if not parsed.netloc or not hostname:
                return f"invalid URL: missing hostname ({raw_url})"
        except Exception as exc:
            return f"URL parse error: {exc}"

        if hostname in self.blocked_hosts or hostname == "localhost":
            return f"SSRF violation: host '{hostname}' is blocked by SSRF policy"

        try:
            if _is_disallowed_ip(hostname):
                return f"SSRF violation: IP '{hostname}' is blocked by SSRF policy (private/loopback/reserved)"
        except ValueError:
            pass

        if self.allowed_domains is not None:
            domain_ok = any(
                hostname == d.lower() or hostname.endswith("." + d.lower())
                for d in self.allowed_domains
            )
            if not domain_ok:
                return f"Envelope violation: domain '{hostname}' is not permitted by adapter allowed_domains"

        if not self.is_simulation:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            try:
                infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            except OSError as exc:
                return f"DNS resolution failed for '{hostname}': {exc}"
            for info in infos:
                sockaddr = info[4]
                if not sockaddr:
                    continue
                ip_str = str(sockaddr[0])
                try:
                    if _is_disallowed_ip(ip_str):
                        return f"Resolved IP '{ip_str}' for '{hostname}' is blocked by SSRF policy (private/loopback/reserved)"
                except ValueError:
                    return f"Unrecognized resolved address '{ip_str}' for '{hostname}'"

        return None

    def execute(self, action: ActionPayload) -> ExecutionReceipt:
        method = action.action_name.lower()
        if method not in self.declared_risks:
            return self._receipt(
                action=action,
                success=False,
                error=f"unsupported HTTP method '{action.action_name}' on adapter '{self.adapter_name}'",
            )

        params = action.params
        raw_url = str(params.get("url") or "")
        if not raw_url:
            return self._receipt(
                action=action,
                success=False,
                error="missing required parameter 'url'",
            )

        url_err = self._validate_url(raw_url)
        if url_err:
            return self._receipt(action=action, success=False, error=url_err)

        headers = dict(self.default_headers)
        if isinstance(params.get("headers"), dict):
            headers.update(params["headers"])

        # Body serialization
        body_bytes: Optional[bytes] = None
        if "json" in params:
            body_bytes = json.dumps(params["json"]).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif "body" in params:
            body_val = params["body"]
            body_bytes = body_val.encode("utf-8") if isinstance(body_val, str) else bytes(body_val)

        timeout = float(params.get("timeout", self.default_timeout))

        # Simulation mode for testing / offline
        if self.is_simulation:
            return self._receipt(
                action=action,
                success=True,
                output={
                    "status_code": 200,
                    "url": raw_url,
                    "method": method.upper(),
                    "headers": {"content-type": "application/json"},
                    "data": {"simulated": True, "method": method.upper(), "url": raw_url},
                },
            )

        # Real HTTP Request
        try:
            req = urllib.request.Request(
                url=raw_url,
                data=body_bytes if method in ("post", "put", "patch") else None,
                headers=headers,
                method=method.upper(),
            )

            start_time = time.time()
            opener = urllib.request.build_opener(self._redirect_handler_cls(self._validate_url))
            with opener.open(req, timeout=timeout) as response:
                content_bytes = response.read(self.max_response_bytes + 1)
                truncated = len(content_bytes) > self.max_response_bytes
                if truncated:
                    content_bytes = content_bytes[: self.max_response_bytes]

                status_code = response.status
                res_headers = dict(response.headers)
                latency = round(time.time() - start_time, 4)

                # Attempt JSON decode
                text_content = content_bytes.decode("utf-8", errors="replace")
                try:
                    data = json.loads(text_content)
                except Exception:
                    data = text_content

                output = {
                    "status_code": status_code,
                    "url": response.geturl(),
                    "headers": res_headers,
                    "data": data,
                    "truncated": truncated,
                    "latency_seconds": latency,
                    "sha256": hashlib.sha256(content_bytes).hexdigest(),
                }

                return self._receipt(
                    action=action,
                    success=status_code < 400,
                    output=output,
                    error=f"HTTP {status_code}" if status_code >= 400 else None,
                )

        except urllib.error.HTTPError as exc:
            err_content = exc.read(4096).decode("utf-8", errors="replace")
            return self._receipt(
                action=action,
                success=False,
                output={"status_code": exc.code, "error_body": err_content},
                error=f"HTTP {exc.code}: {exc.reason}",
            )
        except urllib.error.URLError as exc:
            return self._receipt(
                action=action,
                success=False,
                error=f"HTTP connection failed: {exc.reason}",
            )
        except Exception as exc:
            return self._receipt(
                action=action,
                success=False,
                error=f"HTTP request error ({type(exc).__name__}): {exc}",
            )
