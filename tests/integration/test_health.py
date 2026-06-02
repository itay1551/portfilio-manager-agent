"""Health checks for UI, orchestrator, and tool agents."""

from __future__ import annotations

import httpx
import pytest

from .conftest import ORCH_BASE, TOOL_PORTS, UI_API_BASE, UI_BASE


@pytest.mark.integration
def test_ui_static_page(http_client: httpx.Client):
    response = http_client.get(f"{UI_BASE}/")
    assert response.status_code == 200


@pytest.mark.integration
def test_orchestrator_health(http_client: httpx.Client):
    response = http_client.get(f"{ORCH_BASE}/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


@pytest.mark.integration
def test_ui_api_health_proxy(http_client: httpx.Client):
    response = http_client.get(f"{UI_API_BASE}/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


@pytest.mark.integration
@pytest.mark.parametrize("port", TOOL_PORTS)
def test_tool_agents_expose_tools(http_client: httpx.Client, port: int):
    response = http_client.get(f"http://localhost:{port}/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)
    assert len(tools) > 0
