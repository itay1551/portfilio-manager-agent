"""Guidelines direct orchestrator vs UI nginx proxy must match."""

from __future__ import annotations

import httpx
import pytest

from .conftest import ORCH_BASE, UI_API_BASE, post_json


@pytest.mark.integration
@pytest.mark.requires_controllers
def test_guidelines_ui_matches_direct_orchestrator(
    http_client: httpx.Client, guidelines_payload: dict[str, str]
):
    direct = post_json(
        http_client,
        f"{ORCH_BASE}/pipeline/guidelines",
        guidelines_payload,
    ).json()
    proxied = post_json(
        http_client,
        f"{UI_API_BASE}/pipeline/guidelines",
        guidelines_payload,
    ).json()

    assert "prohibited_tickers" in direct
    assert "prohibited_tickers" in proxied
    assert proxied["prohibited_tickers"] == direct["prohibited_tickers"]
