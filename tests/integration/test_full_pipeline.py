"""Monolithic POST /pipeline integration test (requires real LLM)."""

from __future__ import annotations

import httpx
import pytest

from .conftest import (
    GUIDELINES_CLIENT,
    MAX_VAR,
    ORCH_BASE,
    PORTFOLIO_VALUE,
    QTY_SYMBOLS,
    LlmConfig,
    portfolio_overlap,
)


@pytest.mark.integration
@pytest.mark.llm
def test_full_pipeline(http_client: httpx.Client, llm_config: LlmConfig):
    response = http_client.post(
        f"{ORCH_BASE}/pipeline",
        json={
            "url_investment_guidelines": GUIDELINES_CLIENT,
            "portfolio_value": PORTFOLIO_VALUE,
            "qty_symbols": QTY_SYMBOLS,
            "max_var": MAX_VAR,
            "config": llm_config.as_payload(),
        },
    )
    assert response.status_code == 200, response.text[:500]
    data = response.json()
    assert not data.get("error")

    portfolio = data["portfolio"]
    value_at_risk = float(data["valueAtRisk"])
    draft_email = data.get("draft_email", "")

    assert len(portfolio) == QTY_SYMBOLS
    assert 0 < value_at_risk <= MAX_VAR
    assert len(draft_email) >= 50
    assert portfolio_overlap(data.get("prohibited_tickers", []), portfolio) == []
    assert not draft_email.lstrip().startswith(("{", "[", "Traceback", "Error"))
