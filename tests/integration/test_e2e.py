"""End-to-end tests replicating the browser UI workflow.

Calls go through the UI nginx proxy (/api/*) — the same path a real
user's browser takes — rather than hitting the orchestrator directly.

Flow:
  1. POST /api/pipeline/guidelines  → prohibited tickers
  2. POST /api/pipeline/portfolio   → build portfolio
  3. POST /api/pipeline/var         → calculate VaR
  4. POST /api/pipeline/email       → LLM drafts client email
  5. POST /api/chat                 → swap a symbol, verify update
"""

from __future__ import annotations

import httpx
import pytest

from .conftest import (
    GUIDELINES_CLIENT,
    MAX_VAR,
    PORTFOLIO_VALUE,
    QTY_SYMBOLS,
    UI_API_BASE,
    LlmConfig,
    portfolio_overlap,
    post_json,
)


def _run_granular_pipeline(
    client: httpx.Client,
    llm_config: LlmConfig | None = None,
) -> dict:
    """Run the full granular pipeline through the UI proxy and return all results."""
    guidelines = post_json(
        client,
        f"{UI_API_BASE}/pipeline/guidelines",
        {"url_investment_guidelines": GUIDELINES_CLIENT},
    ).json()
    prohibited = guidelines["prohibited_tickers"]
    assert isinstance(prohibited, list)
    assert len(prohibited) > 0

    portfolio_resp = post_json(
        client,
        f"{UI_API_BASE}/pipeline/portfolio",
        {
            "portfolio_value": PORTFOLIO_VALUE,
            "qty_symbols": QTY_SYMBOLS,
            "prohibited_tickers": prohibited,
        },
    ).json()
    portfolio = portfolio_resp["portfolio"]
    assert len(portfolio) == QTY_SYMBOLS
    assert portfolio_overlap(prohibited, portfolio) == []

    var_resp = post_json(
        client,
        f"{UI_API_BASE}/pipeline/var",
        {"portfolio": portfolio},
    ).json()
    value_at_risk = float(var_resp["valueAtRisk"])
    assert value_at_risk > 0

    result = {
        "prohibited_tickers": prohibited,
        "portfolio": portfolio,
        "valueAtRisk": value_at_risk,
        "guidelines_raw": guidelines,
    }

    if llm_config:
        email_resp = post_json(
            client,
            f"{UI_API_BASE}/pipeline/email",
            {
                "portfolio": portfolio,
                "prohibited_tickers": prohibited,
                "valueAtRisk": value_at_risk,
                "config": llm_config.as_payload(),
            },
        ).json()
        result["draft_email"] = email_resp.get("draft_email", "")

    return result


@pytest.mark.integration
@pytest.mark.llm
def test_e2e_pipeline_with_email(http_client: httpx.Client, llm_config: LlmConfig):
    """Full pipeline through UI proxy: guidelines → portfolio → VaR → email."""
    result = _run_granular_pipeline(http_client, llm_config)

    assert len(result["portfolio"]) == QTY_SYMBOLS
    assert 0 < result["valueAtRisk"] <= MAX_VAR

    draft = result["draft_email"]
    assert len(draft) >= 50, f"Email too short ({len(draft)} chars)"
    assert not draft.lstrip().startswith(("{", "[", "Traceback", "Error"))


@pytest.mark.integration
@pytest.mark.llm
def test_e2e_chat_swap_symbol(http_client: httpx.Client, llm_config: LlmConfig):
    """Pipeline + Phase 2 chat: reject first holding, verify swap via UI proxy."""
    pipeline = _run_granular_pipeline(http_client, llm_config)

    context = {
        "portfolio": pipeline["portfolio"],
        "prohibited_tickers": pipeline["prohibited_tickers"],
        "valueAtRisk": pipeline["valueAtRisk"],
    }
    disliked = pipeline["portfolio"][0]["symbol"]
    var_before = pipeline["valueAtRisk"]

    chat = http_client.post(
        f"{UI_API_BASE}/chat",
        json={
            "message": (
                f"I do not like {disliked} in this portfolio. "
                "Please suggest a replacement and update the holdings."
            ),
            "history": [],
            "context": context,
            "config": llm_config.as_payload(),
        },
    )
    assert chat.status_code == 200, chat.text[:500]
    data = chat.json()
    assert not data.get("error"), f"Chat error: {data.get('error')}"
    assert len(data.get("content", "")) >= 30

    updated = data["context"]
    updated_portfolio = updated["portfolio"]
    updated_var = float(updated["valueAtRisk"])
    updated_symbols = [row["symbol"] for row in updated_portfolio]

    assert len(updated_portfolio) == QTY_SYMBOLS
    assert updated_var > 0
    assert updated_var != var_before
    assert disliked not in updated_symbols
    assert (
        portfolio_overlap(updated.get("prohibited_tickers", []), updated_portfolio)
        == []
    )

    original_symbols = {row["symbol"] for row in pipeline["portfolio"]}
    kept = len(original_symbols & set(updated_symbols))
    assert kept >= QTY_SYMBOLS - 1
