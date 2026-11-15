"""
OpenRouter API Adapter for Governed LLM Inference (Law 2, Law 6).

Provides governed interaction with OpenRouter's unified LLM API over standard
HTTPS. Operates under Orrery's gate ladder, tracking token quotas, enforcing model
allowlists, recording execution receipts with payload digests, and providing
an air-gapped simulation mode when running without credentials.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence, Union

from orrery.adapters.base import BaseAdapter
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
OPENROUTER_ENV_KEY = "OPENROUTER_API_KEY"


class OpenRouterAdapter(BaseAdapter):
    """
    Adapter for invoking large language models via OpenRouter.
    """

    adapter_name = "openrouter"
    target_params: ClassVar[tuple] = ()

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        "chat_completion": ActionRisk.READ_ONLY,
        "generate_text": ActionRisk.READ_ONLY,
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = OPENROUTER_API_URL,
        default_model: str = DEFAULT_MODEL,
        allowed_models: Optional[Sequence[str]] = None,
        max_tokens_limit: int = 4096,
        timeout_seconds: float = 30.0,
        is_simulation: bool = False,
        site_url: str = "https://github.com/kirklasalle/orrery",
        site_name: str = "Orrery Autonomous Governance",
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name=self.adapter_name, config=config)
        self.api_key = api_key or os.environ.get(OPENROUTER_ENV_KEY, "")
        self.base_url = base_url
        self.default_model = default_model
        self.allowed_models = set(allowed_models) if allowed_models else None
        self.max_tokens_limit = max_tokens_limit
        self.timeout_seconds = timeout_seconds
        self.is_simulation = is_simulation
        self.site_url = site_url
        self.site_name = site_name

    def classify_risk(self, action: ActionPayload) -> ActionRisk:
        return self.risk_for(action.action_name)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "adapter": self.adapter_name,
            "default_model": self.default_model,
            "has_api_key": bool(self.api_key),
            "is_simulation": self.is_simulation,
            "max_tokens_limit": self.max_tokens_limit,
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        return self.execute(action)

    def execute(self, action: ActionPayload) -> ExecutionReceipt:
        action_name = action.action_name
        params = action.params

        if action_name not in ("chat_completion", "generate_text"):
            return self._receipt(
                action=action,
                success=False,
                error=f"unknown action '{action_name}' on adapter '{self.adapter_name}'",
            )

        model = str(params.get("model") or self.default_model)
        if self.allowed_models and model not in self.allowed_models:
            return self._receipt(
                action=action,
                success=False,
                error=f"model '{model}' is not permitted by model allowlist",
            )

        max_tokens = int(params.get("max_tokens", 1000))
        if max_tokens > self.max_tokens_limit:
            return self._receipt(
                action=action,
                success=False,
                error=f"requested max_tokens {max_tokens} exceeds adapter limit {self.max_tokens_limit}",
            )

        if action_name == "generate_text":
            prompt = str(params.get("prompt", ""))
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = params.get("messages", [])
            if not isinstance(messages, list):
                return self._receipt(
                    action=action,
                    success=False,
                    error="params['messages'] must be a list of message dicts",
                )

        temperature = float(params.get("temperature", 0.7))
        response_format = params.get("response_format")

        # Simulation mode when explicitly requested
        if self.is_simulation:
            simulated_response = self._simulate_response(
                model=model,
                messages=messages,
                response_format=response_format,
            )
            return self._receipt(
                action=action,
                success=True,
                output=simulated_response,
            )

        if not self.api_key:
            return self._receipt(
                action=action,
                success=False,
                error="ADP-011: OpenRouterAdapter requires api_key when is_simulation=False",
            )

        # Real OpenRouter API call
        request_body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            request_body["response_format"] = response_format

        try:
            req_data = json.dumps(request_body).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.site_url,
                "X-Title": self.site_name,
            }
            req = urllib.request.Request(
                url=self.base_url,
                data=req_data,
                headers=headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                res_bytes = response.read()
                data = json.loads(res_bytes.decode("utf-8"))

            return self._receipt(
                action=action,
                success=True,
                output=data,
            )

        except urllib.error.HTTPError as exc:
            error_msg = f"OpenRouter HTTP {exc.code}: {exc.reason}"
            try:
                err_body = exc.read().decode("utf-8")
                error_msg += f" - {err_body}"
            except Exception:
                pass
            return self._receipt(
                action=action,
                success=False,
                error=error_msg,
            )
        except urllib.error.URLError as exc:
            return self._receipt(
                action=action,
                success=False,
                error=f"OpenRouter connection error: {exc.reason}",
            )
        except Exception as exc:
            return self._receipt(
                action=action,
                success=False,
                error=f"OpenRouter request failed ({type(exc).__name__}): {exc}",
            )

    def _simulate_response(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Provides a deterministic air-gapped response for testing and offline runs."""
        last_message = messages[-1]["content"] if messages else ""

        # If a JSON response format was requested (e.g. from LLM-as-judge)
        if response_format and response_format.get("type") == "json_object":
            sim_content = json.dumps({
                "verified": True,
                "confidence": 0.95,
                "detail": "Simulated verification: all planned action receipts completed successfully.",
                "identified_defects": [],
            })
        else:
            sim_content = (
                f"[SIMULATED OPENROUTER RESPONSE from {model}] "
                f"Processed {len(messages)} message(s). Last prompt snippet: {str(last_message)[:60]}"
            )

        return {
            "id": f"sim-{hashlib.sha256(str(messages).encode()).hexdigest()[:12]}",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": sim_content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "model": model,
            "usage": {
                "prompt_tokens": len(str(messages)) // 4,
                "completion_tokens": len(sim_content) // 4,
                "total_tokens": (len(str(messages)) + len(sim_content)) // 4,
            },
            "simulated": True,
        }
