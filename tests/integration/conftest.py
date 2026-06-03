"""Fixtures for local integration tests against a running Podman Compose stack."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = Path(os.getenv("ENV_FILE", ROOT / ".env"))

GUIDELINES_CLIENT = os.getenv("GUIDELINES_URL", "100")
PORTFOLIO_VALUE = int(os.getenv("PORTFOLIO_VALUE", "1000000"))
QTY_SYMBOLS = int(os.getenv("QTY_SYMBOLS", "5"))
MAX_VAR = float(os.getenv("MAX_VAR", "35000"))
HTTP_TIMEOUT = float(os.getenv("CURL_MAX_TIME", "60"))

UI_BASE = os.getenv("UI_BASE", "http://localhost:8080").rstrip("/")
ORCH_BASE = os.getenv("ORCH_BASE", "http://localhost:5000").rstrip("/")
UI_API_BASE = f"{UI_BASE}/api"
TOOL_PORTS = (7001, 7002, 7003)


@dataclass
class LlmConfig:
    llm_url: str
    api_key: str
    model: str

    @property
    def is_real(self) -> bool:
        if not self.llm_url or not self.api_key or not self.model:
            return False
        placeholders = ("your-", "example.com", "sk-your")
        combined = f"{self.llm_url} {self.api_key} {self.model}".lower()
        return not any(token in combined for token in placeholders)

    def as_payload(self) -> dict[str, str]:
        return {
            "llmUrl": self.llm_url,
            "apiKey": self.api_key,
            "model": self.model,
        }


def load_llm_config() -> LlmConfig:
    values = dotenv_values(ENV_FILE) if ENV_FILE.is_file() else {}
    return LlmConfig(
        llm_url=os.getenv("OPENAI_API_ENDPOINT", values.get("OPENAI_API_ENDPOINT", "")),
        api_key=os.getenv("OPENAI_API_TOKEN", values.get("OPENAI_API_TOKEN", "")),
        model=os.getenv("OPENAI_MODEL", values.get("OPENAI_MODEL", "")),
    )


def assert_stack_ready() -> None:
    probes = [
        ("orchestrator health", f"{ORCH_BASE}/health"),
        ("UI static", f"{UI_BASE}/"),
        ("UI api health", f"{UI_API_BASE}/health"),
    ]
    if "localhost" in UI_BASE:
        for port in TOOL_PORTS:
            probes.append((f"tool {port}", f"http://localhost:{port}/tools"))

    with httpx.Client(timeout=10.0) as client:
        for label, url in probes:
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"{label} unreachable at {url}: {exc}. "
                    "Start the stack with: make deploy-local"
                ) from exc
            if response.status_code != 200:
                raise RuntimeError(
                    f"{label} returned HTTP {response.status_code} at {url}. "
                    "Start the stack with: make deploy-local"
                )


@pytest.fixture(scope="session")
def require_stack():
    assert_stack_ready()


@pytest.fixture
def http_client(require_stack):
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        yield client


@pytest.fixture
def llm_config():
    config = load_llm_config()
    if not config.is_real:
        pytest.skip(
            f"Set real OPENAI_API_* values in {ENV_FILE} for LLM integration tests"
        )
    return config


@pytest.fixture
def guidelines_payload() -> dict[str, str]:
    return {"url_investment_guidelines": GUIDELINES_CLIENT}


def post_json(client: httpx.Client, url: str, payload: dict) -> httpx.Response:
    response = client.post(url, json=payload)
    assert response.status_code == 200, (
        f"POST {url} returned HTTP {response.status_code}: {response.text[:300]}"
    )
    return response


def portfolio_overlap(prohibited: list[str], portfolio: list[dict]) -> list[str]:
    banned = {symbol.upper() for symbol in prohibited}
    held = {str(row.get("symbol", "")).upper() for row in portfolio}
    return sorted(banned & held)
