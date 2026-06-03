"""Tool agent discovery smoke checks."""

from __future__ import annotations

import httpx
import pytest

from .conftest import TOOL_PORTS


@pytest.mark.integration
@pytest.mark.local_only
@pytest.mark.parametrize("port", TOOL_PORTS)
def test_tools_endpoint_non_empty(http_client: httpx.Client, port: int):
    tools = http_client.get(f"http://localhost:{port}/tools").json()
    names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
    assert names


@pytest.mark.integration
@pytest.mark.local_only
def test_portfolio_agent_has_replace_symbol(http_client: httpx.Client):
    tools = http_client.get("http://localhost:7002/tools").json()
    names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
    assert "portfolio_replace_symbol" in names
