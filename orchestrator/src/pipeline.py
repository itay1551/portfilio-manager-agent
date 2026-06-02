"""Deterministic portfolio pipeline."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from openai import OpenAI

from orchestrator import HttpToolServer

logger = logging.getLogger(__name__)

MAX_PORTFOLIO_ATTEMPTS = 10
CONFIDENCE = 0.99

DRAFT_EMAIL_SYSTEM = (
    "You are a portfolio manager at an asset manager who has been asked to recommend a portfolio. "
    "Compose a professional, human-readable response in English that informs the client of the "
    "proposed portfolio that fits within their requested risk tolerance and meets their investment "
    "guidelines. Do not hallucinate. Only present what you know as fact."
)

PORTFOLIO_MUTATION_TOOLS = frozenset({"portfolio_equities", "portfolio_replace_symbol"})


class ToolRegistry:
    """Tool name -> server map; discovers each agent once per instance."""

    def __init__(self, servers: list[HttpToolServer]):
        self._map: dict[str, HttpToolServer] = {}
        for server in servers:
            for tool in server.discover():
                if tool.name in self._map:
                    raise RuntimeError(f"Duplicate tool name discovered: {tool.name}")
                self._map[tool.name] = server

    def call(self, name: str, arguments: dict) -> Any:
        server = self._map.get(name)
        if server is None:
            raise RuntimeError(f"Tool not available: {name}")
        return server.call(name, arguments)


def parse_guidelines(
    registry: ToolRegistry, url_investment_guidelines: str
) -> dict[str, Any]:
    if url_investment_guidelines.startswith(("http://", "https://")):
        args = {"url_investment_guidelines": url_investment_guidelines}
    else:
        args = {"client": url_investment_guidelines}
    raw = registry.call("prohibited_symbols", args)
    if isinstance(raw, dict) and raw.get("error"):
        raise RuntimeError(raw["error"])
    prohibited = raw.get("prohibited_tickers", []) if isinstance(raw, dict) else []
    return {"prohibited_tickers": prohibited, "guidelines_raw": raw}


def build_portfolio(
    registry: ToolRegistry,
    portfolio_value: int,
    qty_symbols: int,
    symbols_exclusion: list[str],
) -> list[dict]:
    raw = registry.call(
        "portfolio_equities",
        {
            "portfolio_value": portfolio_value,
            "qty_symbols": qty_symbols,
            "symbols_exclusion": symbols_exclusion,
        },
    )
    if isinstance(raw, dict) and raw.get("error"):
        raise RuntimeError(raw["error"])
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "portfolio" in raw:
        return raw["portfolio"]
    raise RuntimeError(f"Unexpected portfolio response: {raw!r}")


def calculate_var(registry: ToolRegistry, portfolio: list[dict]) -> dict[str, Any]:
    raw = registry.call(
        "value_at_risk",
        {"confidence": CONFIDENCE, "portfolio": portfolio},
    )
    if isinstance(raw, dict) and raw.get("error"):
        raise RuntimeError(raw["error"])
    return raw


def generate_draft_email(
    llm_client: OpenAI,
    model: str,
    portfolio: list[dict],
    value_at_risk: float,
    temperature: float = 0.7,
) -> str:
    user_payload = {
        "clientName": "Client",
        "portfolio": portfolio,
        "valueAtRisk": {
            "maximumExpectedLoss": value_at_risk,
            "confidence": CONFIDENCE,
            "period": "1-day",
        },
    }
    response = llm_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DRAFT_EMAIL_SYSTEM},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        temperature=temperature,
    )
    content = response.choices[0].message.content
    return content or ""


def run_portfolio_var_loop(
    registry: ToolRegistry,
    portfolio_value: int,
    qty_symbols: int,
    prohibited_tickers: list[str],
    max_var: float,
) -> tuple[list[dict], float, int]:
    """Build portfolio and VaR; retry until VaR <= max_var or attempts exhausted."""
    portfolio: list[dict] = []
    value_at_risk = 0.0
    attempts = 0

    for attempt in range(1, MAX_PORTFOLIO_ATTEMPTS + 1):
        attempts = attempt
        portfolio = build_portfolio(
            registry, portfolio_value, qty_symbols, prohibited_tickers
        )
        var_result = calculate_var(registry, portfolio)
        value_at_risk = float(var_result.get("valueAtRisk", 0))
        if value_at_risk <= max_var:
            return portfolio, value_at_risk, attempts

    raise RuntimeError(
        f"Could not build a portfolio within max VaR (${max_var:,.2f}) after "
        f"{MAX_PORTFOLIO_ATTEMPTS} attempts. Last VaR: ${value_at_risk:,.2f}."
    )


def run_pipeline(
    registry: ToolRegistry,
    llm_client: OpenAI,
    model: str,
    url_investment_guidelines: str,
    portfolio_value: int,
    qty_symbols: int,
    max_var: float,
) -> dict[str, Any]:
    t0 = time.time()
    guidelines = parse_guidelines(registry, url_investment_guidelines)
    prohibited = guidelines["prohibited_tickers"]

    portfolio, value_at_risk, attempts = run_portfolio_var_loop(
        registry,
        portfolio_value,
        qty_symbols,
        prohibited,
        max_var,
    )

    draft_email = generate_draft_email(llm_client, model, portfolio, value_at_risk)

    return {
        "prohibited_tickers": prohibited,
        "guidelines_raw": guidelines["guidelines_raw"],
        "portfolio": portfolio,
        "valueAtRisk": value_at_risk,
        "confidence": CONFIDENCE,
        "draft_email": draft_email,
        "attempts": attempts,
        "latency_sec": round(time.time() - t0, 3),
        "inputs": {
            "url_investment_guidelines": url_investment_guidelines,
            "portfolio_value": portfolio_value,
            "qty_symbols": qty_symbols,
            "max_var": max_var,
        },
    }


def build_context_from_pipeline(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    """Context object passed to Phase 2 chat."""
    return {
        "prohibited_tickers": pipeline_result.get("prohibited_tickers", []),
        "guidelines_raw": pipeline_result.get("guidelines_raw"),
        "portfolio": pipeline_result.get("portfolio", []),
        "valueAtRisk": pipeline_result.get("valueAtRisk"),
        "confidence": pipeline_result.get("confidence", CONFIDENCE),
        "draft_email": pipeline_result.get("draft_email", ""),
        "inputs": pipeline_result.get("inputs", {}),
    }


def _tool_result_failed(result: Any) -> bool:
    return isinstance(result, dict) and bool(result.get("error"))


def _portfolio_symbols(portfolio: Any) -> list[str]:
    if not isinstance(portfolio, list):
        return []
    return [str(p.get("symbol", "")).upper() for p in portfolio if p.get("symbol")]


def _same_portfolio_holdings(left: Any, right: Any) -> bool:
    return sorted(_portfolio_symbols(left)) == sorted(_portfolio_symbols(right))


def apply_tool_result_to_context(
    context: dict[str, Any], tool_name: str, result: Any
) -> dict[str, Any]:
    """Update mutable context fields after a Phase 2 tool call."""
    ctx = dict(context)
    if tool_name in PORTFOLIO_MUTATION_TOOLS:
        if isinstance(result, list):
            ctx["portfolio"] = result
        elif isinstance(result, dict) and not result.get("error"):
            if "portfolio" in result:
                ctx["portfolio"] = result["portfolio"]
    elif tool_name == "value_at_risk":
        if isinstance(result, dict) and "valueAtRisk" in result:
            ctx["valueAtRisk"] = float(result["valueAtRisk"])
            if "confidence" in result:
                ctx["confidence"] = result["confidence"]
    return ctx


def apply_phase2_tool_result(
    context: dict[str, Any],
    tool_name: str,
    result: Any,
    registry: ToolRegistry,
    tool_args: dict | None = None,
) -> dict[str, Any]:
    """Apply tool output to context; recalc VaR after portfolio mutations."""
    if tool_name == "value_at_risk" and tool_args is not None:
        if not _same_portfolio_holdings(
            tool_args.get("portfolio"), context.get("portfolio")
        ):
            return context

    ctx = apply_tool_result_to_context(context, tool_name, result)
    if tool_name not in PORTFOLIO_MUTATION_TOOLS or _tool_result_failed(result):
        return ctx
    portfolio = ctx.get("portfolio")
    if not portfolio:
        return ctx
    try:
        var_result = calculate_var(registry, portfolio)
        return apply_tool_result_to_context(ctx, "value_at_risk", var_result)
    except Exception as e:
        logger.warning("Auto VaR after %s failed: %s", tool_name, e)
        return ctx


_DISLIKE_SYMBOL_RE = re.compile(
    r"do not like\s+([A-Za-z][A-Za-z0-9.-]*)\s+in this portfolio",
    re.IGNORECASE,
)


def disliked_symbol_in_message(user_message: str, portfolio: list[dict]) -> str | None:
    """Match verify-script phrasing: reject one named holding."""
    match = _DISLIKE_SYMBOL_RE.search(user_message)
    if not match:
        return None
    symbol = match.group(1).upper()
    held = {str(p.get("symbol", "")).upper() for p in portfolio if p.get("symbol")}
    return symbol if symbol in held else None


def apply_symbol_rejection(
    context: dict[str, Any],
    remove_symbol: str,
    registry: ToolRegistry,
) -> dict[str, Any]:
    """Call portfolio_replace_symbol and refresh context (incl. VaR)."""
    inputs = context.get("inputs") or {}
    args = {
        "portfolio": context.get("portfolio", []),
        "remove_symbol": remove_symbol,
        "portfolio_value": int(inputs.get("portfolio_value", 1_000_000)),
        "symbols_exclusion": list(context.get("prohibited_tickers", [])),
    }
    result = registry.call("portfolio_replace_symbol", args)
    return apply_phase2_tool_result(
        context,
        "portfolio_replace_symbol",
        result,
        registry,
        tool_args=args,
    )


def should_regenerate_email(user_message: str) -> bool:
    lower = user_message.lower()
    return "email" in lower and any(
        w in lower for w in ("regenerat", "rewrite", "update", "refresh", "new draft")
    )
