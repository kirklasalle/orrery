"""
Tests for Governed HTTP/REST Adapter.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from orrery.adapters.http import HttpAdapter
from orrery.core.types import ActionPayload, ActionRisk, CycleTier, StateContext


def test_http_adapter_risk_classification():
    adapter = HttpAdapter()
    assert adapter.classify_risk(ActionPayload(action_name="get", params={"url": "https://api.example.com"}, tier=CycleTier.MICRO, target_adapter="http")) == ActionRisk.READ_ONLY
    assert adapter.classify_risk(ActionPayload(action_name="head", params={"url": "https://api.example.com"}, tier=CycleTier.MICRO, target_adapter="http")) == ActionRisk.READ_ONLY
    assert adapter.classify_risk(ActionPayload(action_name="post", params={"url": "https://api.example.com"}, tier=CycleTier.MICRO, target_adapter="http")) == ActionRisk.COMPENSABLE
    assert adapter.classify_risk(ActionPayload(action_name="put", params={"url": "https://api.example.com"}, tier=CycleTier.MICRO, target_adapter="http")) == ActionRisk.COMPENSABLE
    assert adapter.classify_risk(ActionPayload(action_name="patch", params={"url": "https://api.example.com"}, tier=CycleTier.MICRO, target_adapter="http")) == ActionRisk.COMPENSABLE
    assert adapter.classify_risk(ActionPayload(action_name="delete", params={"url": "https://api.example.com"}, tier=CycleTier.MICRO, target_adapter="http")) == ActionRisk.IRREVERSIBLE


def test_http_adapter_missing_or_invalid_url():
    adapter = HttpAdapter()

    # Missing url
    r1 = adapter.execute(ActionPayload(action_name="get", params={}, tier=CycleTier.MICRO, target_adapter="http"))
    assert not r1.success
    assert "missing required parameter 'url'" in r1.error

    # Invalid scheme
    r2 = adapter.execute(ActionPayload(action_name="get", params={"url": "ftp://ftp.example.com/file"}, tier=CycleTier.MICRO, target_adapter="http"))
    assert not r2.success
    assert "unsupported URL scheme" in r2.error

    # Missing hostname
    r3 = adapter.execute(ActionPayload(action_name="get", params={"url": "https://"}, tier=CycleTier.MICRO, target_adapter="http"))
    assert not r3.success
    assert "missing hostname" in r3.error


def test_http_adapter_ssrf_protection():
    adapter = HttpAdapter()
    # Cloud metadata endpoint
    act = ActionPayload(action_name="get", params={"url": "http://169.254.169.254/latest/meta-data"}, tier=CycleTier.MICRO, target_adapter="http")
    receipt = adapter.execute(act)
    assert not receipt.success
    assert "SSRF violation" in receipt.error


def test_http_adapter_domain_allowlist():
    adapter = HttpAdapter(allowed_domains=["api.example.com", "github.com"])

    # Permitted domain
    r_ok = adapter.execute(ActionPayload(action_name="get", params={"url": "https://api.example.com/v1/users"}, tier=CycleTier.MICRO, target_adapter="http"))
    # In non-simulation mode without net, fails with URLError/HTTP error, NOT envelope violation
    assert "Envelope violation" not in (r_ok.error or "")

    # Disallowed domain
    r_deny = adapter.execute(ActionPayload(action_name="get", params={"url": "https://malicious.evil.com/leak"}, tier=CycleTier.MICRO, target_adapter="http"))
    assert not r_deny.success
    assert "Envelope violation" in r_deny.error


def test_http_adapter_simulation_mode():
    adapter = HttpAdapter(is_simulation=True)
    act = ActionPayload(
        action_name="post",
        params={"url": "https://api.example.com/data", "json": {"name": "test"}},
        tier=CycleTier.MICRO,
        target_adapter="http",
    )
    receipt = adapter.execute(act)
    assert receipt.success
    assert receipt.output["status_code"] == 200
    assert receipt.output["data"]["simulated"] is True


def test_http_adapter_mocked_request_success():
    adapter = HttpAdapter()
    act = ActionPayload(
        action_name="get",
        params={"url": "https://api.example.com/items"},
        tier=CycleTier.MICRO,
        target_adapter="http",
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.geturl.return_value = "https://api.example.com/items"
    mock_resp.read.return_value = b'{"items": [1, 2, 3]}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        receipt = adapter.execute(act)

    assert receipt.success
    assert receipt.output["status_code"] == 200
    assert receipt.output["data"] == {"items": [1, 2, 3]}
    assert "sha256" in receipt.output


def test_http_adapter_mocked_http_error():
    adapter = HttpAdapter()
    act = ActionPayload(
        action_name="delete",
        params={"url": "https://api.example.com/items/99"},
        tier=CycleTier.MICRO,
        target_adapter="http",
    )

    import urllib.error
    mock_err = urllib.error.HTTPError("https://api.example.com/items/99", 404, "Not Found", {}, None)
    mock_err.read = MagicMock(return_value=b"Item not found")

    with patch("urllib.request.urlopen", side_effect=mock_err):
        receipt = adapter.execute(act)

    assert not receipt.success
    assert "HTTP 404" in receipt.error


@pytest.mark.asyncio
async def test_http_adapter_async_interface():
    adapter = HttpAdapter(is_simulation=True)
    context = StateContext()
    env = await adapter.perceive_environment(context)
    assert env["adapter"] == "http"
    assert env["is_simulation"] is True

    act = ActionPayload(
        action_name="get",
        params={"url": "https://api.example.com/test"},
        tier=CycleTier.MICRO,
        target_adapter="http",
    )
    receipt = await adapter.execute_action(act)
    assert receipt.success
