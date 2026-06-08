"""Optional NeMo Guardrails validation sidecar client.

Calls the /v1/guardrail/checks endpoint to validate messages against
configured rails (PII detection, regex patterns, custom actions).
Gracefully degrades: if GUARDRAILS_URL is unset or the service is
unreachable, all messages are allowed through.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "").rstrip("/")
_TIMEOUT = float(os.getenv("GUARDRAILS_TIMEOUT", "10"))


@dataclass
class CheckResult:
    allowed: bool
    detail: str


def _check(messages: list[dict], model: str = "test") -> CheckResult:
    """Call /v1/guardrail/checks and return pass/block result."""
    if not GUARDRAILS_URL:
        return CheckResult(allowed=True, detail="guardrails not configured")

    url = f"{GUARDRAILS_URL}/v1/guardrail/checks"
    payload = {"model": model, "messages": messages}
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as exc:
        logger.warning(f"Guardrails service unreachable: {exc}")
        return CheckResult(allowed=True, detail=f"guardrails unavailable: {exc}")

    status = body.get("status", "success")
    if status == "blocked":
        rails_status = body.get("rails_status", {})
        triggered = [
            name
            for name, info in rails_status.items()
            if isinstance(info, dict) and info.get("status") == "blocked"
        ]
        detail = (
            f"Blocked by guardrails: {', '.join(triggered)}"
            if triggered
            else "Blocked by guardrails"
        )
        return CheckResult(allowed=False, detail=detail)

    return CheckResult(allowed=True, detail="passed")


def check_input(user_message: str) -> CheckResult:
    """Validate a user message before sending to the LLM."""
    return _check([{"role": "user", "content": user_message}])


def check_output(user_message: str, bot_response: str) -> CheckResult:
    """Validate an LLM response before returning to the user."""
    return _check(
        [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": bot_response},
        ]
    )


def is_enabled() -> bool:
    return bool(GUARDRAILS_URL)
