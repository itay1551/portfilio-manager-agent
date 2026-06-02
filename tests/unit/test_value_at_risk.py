"""Unit tests for parametric VaR calculation with synthetic market data."""

from __future__ import annotations

import pandas as pd
import pytest

from portfolio import Portfolio
from value_at_risk import ValueAtRisk


def _sample_portfolio() -> Portfolio:
    portfolio = Portfolio()
    portfolio.addPosition("AAPL", quantity=100, price=150.0)
    portfolio.addPosition("MSFT", quantity=50, price=300.0)
    return portfolio


def _sample_market_data() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    return pd.DataFrame(
        {
            "AAPL": [150.0, 151.0, 149.0, 150.5, 152.0, 151.0],
            "MSFT": [300.0, 302.0, 298.0, 301.0, 303.0, 300.5],
        },
        index=dates,
    )


@pytest.mark.unit
def test_value_at_risk_returns_positive_dollar_amount():
    portfolio = _sample_portfolio()
    market_data = _sample_market_data()

    var = ValueAtRisk().calculate(portfolio, market_data, confidence=0.99)

    assert isinstance(var, float)
    assert var > 0


@pytest.mark.unit
def test_portfolio_mtm_and_weights():
    portfolio = _sample_portfolio()

    assert portfolio.mtm() == pytest.approx(100 * 150.0 + 50 * 300.0)
    weights = portfolio.weights()
    assert len(weights) == 2
    assert weights.sum() == pytest.approx(1.0)
