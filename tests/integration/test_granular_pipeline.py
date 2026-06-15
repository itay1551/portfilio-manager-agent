"""Granular pipeline steps 2–3 via UI nginx proxy (browser path)."""

from __future__ import annotations

import httpx
import pytest

from .conftest import (
    PORTFOLIO_VALUE,
    QTY_SYMBOLS,
    UI_API_BASE,
    portfolio_overlap,
    post_json,
)


@pytest.mark.integration
@pytest.mark.requires_controllers
def test_granular_pipeline_portfolio_and_var(
    http_client: httpx.Client, guidelines_payload: dict[str, str]
):
    guidelines = post_json(
        http_client,
        f"{UI_API_BASE}/pipeline/guidelines",
        guidelines_payload,
    ).json()
    prohibited = guidelines["prohibited_tickers"]

    portfolio_response = post_json(
        http_client,
        f"{UI_API_BASE}/pipeline/portfolio",
        {
            "portfolio_value": PORTFOLIO_VALUE,
            "qty_symbols": QTY_SYMBOLS,
            "prohibited_tickers": prohibited,
        },
    ).json()
    portfolio = portfolio_response["portfolio"]
    assert len(portfolio) == QTY_SYMBOLS
    assert portfolio_overlap(prohibited, portfolio) == []

    var_response = post_json(
        http_client,
        f"{UI_API_BASE}/pipeline/var",
        {"portfolio": portfolio},
    ).json()
    value_at_risk = float(var_response["valueAtRisk"])
    assert value_at_risk > 0
