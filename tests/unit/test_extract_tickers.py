"""Unit tests for guidelines ticker extraction heuristics."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "guidelines_app",
    ROOT / "tools/guidelines/src/app.py",
)
assert _spec and _spec.loader
guidelines_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guidelines_app)


@pytest.mark.unit
def test_split_sentences_splits_on_blank_lines():
    text = "First sentence.\n\nSecond sentence."
    parts = guidelines_app.split_sentences(text)
    assert "First sentence." in parts[0]
    assert any("Second sentence" in part for part in parts)


@pytest.mark.unit
def test_extract_tickers_finds_symbols_with_prohibition_cues():
    line = "The fund must not hold CVX, XOM, or TGT."
    tickers = guidelines_app.extract_tickers(line)
    assert "CVX" in tickers
    assert "XOM" in tickers
    assert "TGT" in tickers


@pytest.mark.unit
def test_extract_tickers_skips_company_name_context():
    line = "Neurosymbolic AI, Inc. provides advisory services."
    tickers = guidelines_app.extract_tickers(line)
    assert "AI" not in tickers


@pytest.mark.unit
def test_extract_tickers_skips_credit_rating_tokens():
    line = "Commercial paper rated AA-1 is acceptable."
    tickers = guidelines_app.extract_tickers(line)
    assert "AA" not in tickers
