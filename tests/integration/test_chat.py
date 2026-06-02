"""Phase 2 chat integration test (requires real LLM)."""

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
def test_chat_rejects_first_holding(http_client: httpx.Client, llm_config: LlmConfig):
    pipeline = http_client.post(
        f"{ORCH_BASE}/pipeline",
        json={
            "url_investment_guidelines": GUIDELINES_CLIENT,
            "portfolio_value": PORTFOLIO_VALUE,
            "qty_symbols": QTY_SYMBOLS,
            "max_var": MAX_VAR,
            "config": llm_config.as_payload(),
        },
    )
    assert pipeline.status_code == 200, pipeline.text[:500]
    pipeline_data = pipeline.json()
    context = pipeline_data["context"]
    var_before = float(pipeline_data["valueAtRisk"])
    disliked_symbol = pipeline_data["portfolio"][0]["symbol"]

    chat = http_client.post(
        f"{ORCH_BASE}/chat",
        json={
            "message": (
                f"I do not like {disliked_symbol} in this portfolio. "
                "Please suggest a replacement and update the holdings."
            ),
            "history": [],
            "context": context,
            "config": llm_config.as_payload(),
        },
    )
    assert chat.status_code == 200, chat.text[:500]
    chat_data = chat.json()
    assert not chat_data.get("error")
    assert len(chat_data.get("content", "")) >= 30

    updated = chat_data["context"]
    assert len(updated["portfolio"]) == QTY_SYMBOLS
    assert float(updated["valueAtRisk"]) > 0
    assert float(updated["valueAtRisk"]) != var_before

    symbols = [row["symbol"] for row in updated["portfolio"]]
    assert disliked_symbol not in symbols
    assert portfolio_overlap(updated.get("prohibited_tickers", []), updated["portfolio"]) == []

    tool_names = [entry.get("name") for entry in chat_data.get("tool_history", [])]
    assert "portfolio_replace_symbol" in tool_names

    original_symbols = {row["symbol"] for row in context["portfolio"]}
    kept = len(original_symbols & set(symbols))
    assert kept >= QTY_SYMBOLS - 1
