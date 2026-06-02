"""Unit tests for parse_guidelines client vs URL routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pipeline import parse_guidelines


@dataclass
class FakeRegistry:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    response: dict[str, Any] = field(
        default_factory=lambda: {"prohibited_tickers": ["CVX", "XOM"]}
    )

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return self.response


@pytest.mark.unit
def test_parse_guidelines_uses_client_for_numeric_id():
    registry = FakeRegistry()
    result = parse_guidelines(registry, "100")

    assert registry.calls == [("prohibited_symbols", {"client": "100"})]
    assert result["prohibited_tickers"] == ["CVX", "XOM"]
    assert result["guidelines_raw"] == registry.response


@pytest.mark.unit
def test_parse_guidelines_uses_url_for_http():
    registry = FakeRegistry()
    url = "https://example.com/guidelines.pdf"
    result = parse_guidelines(registry, url)

    assert registry.calls == [
        ("prohibited_symbols", {"url_investment_guidelines": url})
    ]
    assert result["prohibited_tickers"] == ["CVX", "XOM"]


@pytest.mark.unit
def test_parse_guidelines_raises_on_tool_error():
    registry = FakeRegistry(response={"error": "PDF not found"})

    with pytest.raises(RuntimeError, match="PDF not found"):
        parse_guidelines(registry, "100")
