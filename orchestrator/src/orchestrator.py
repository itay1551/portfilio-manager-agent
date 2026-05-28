import os
import json
import time
import typing as t
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from flask import Flask, request, jsonify
from openai import OpenAI

# ----------------------------
# Models & Helpers
# ----------------------------

@dataclass
class DiscoveredTool:
    name: str
    description: str
    parameters: dict   # JSON Schema
    server_base: str   # which HTTP server hosts it

def _get_env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

# ----------------------------
# HTTP Tool Server Adapter (same simple shape)
# ----------------------------

class HttpToolServer:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def discover(self) -> list[DiscoveredTool]:
        url = urljoin(self.base_url, "tools")
        print(f"Fetching tool schema from: {url}")
        resp = requests.get(url, timeout=self.timeout)
        print(f"Schema: {resp.json()}")
        resp.raise_for_status()
        tools = []
        for item in resp.json():
            tools.append(
                DiscoveredTool(
                    name        = item["name"],
                    description = item.get("description", ""),
                    parameters  = item.get("parameters", {"type": "object", "properties": {}}),
                    server_base = self.base_url
                )
            )
        return tools

    def call(self, tool_name: str, arguments: dict) -> dict:
        url = urljoin(self.base_url, f"tools/{tool_name}")
        resp = requests.post(url, json=arguments, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

# -----------------------------
# MCP style client Orchestrator
# -----------------------------

class Orchestrator:
    def __init__(self, openai_client: OpenAI, model: str, servers: list[HttpToolServer], request_timeout: float = 60.0):
        self.openai = openai_client
        self.model = model
        self.servers = servers
        self.request_timeout = request_timeout
        self.tool_registry: dict[str, DiscoveredTool] = {}
        self.server_index: dict[str, HttpToolServer] = {s.base_url: s for s in servers}

    def refresh_tools(self) -> list[dict]:
        self.tool_registry.clear()
        advertised: list[dict] = []
        for server in self.servers:
            for tool in server.discover():
                if tool.name in self.tool_registry:
                    # namespace duplicates by host if needed
                    raise ValueError(f"Duplicate tool name discovered: {tool.name}")
                self.tool_registry[tool.name] = tool
                advertised.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "server_base": tool.server_base
                })
        return advertised

    def tools_payload(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t_.name,
                    "description": t_.description,
                    "parameters": t_.parameters,
                }
            }
            for t_ in self.tool_registry.values()
        ]
        #return [
        #    {
        #        "type": "function",
        #        "name": t_.name,
        #        "description": t_.description,
        #        "parameters": t_.parameters,
        #    }
        #    for t_ in self.tool_registry.values()
        #]

    def _execute_tool_call(self, name: str, arguments_json: str | dict) -> dict:
        tool = self.tool_registry.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            args = json.loads(arguments_json) if isinstance(arguments_json, str) else (arguments_json or {})
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON args for {name}: {e}"}

        server = self.server_index.get(tool.server_base)
        if not server:
            return {"error": f"No server bound for tool {name}"}
        try:
            return server.call(name, args)
        except requests.HTTPError as e:
            return {"error": f"HTTP error from {name}: {e.response.status_code} {e.response.text}"}
        except Exception as e:
            return {"error": f"Tool {name} failed: {e}"}
        

    def chat_agentic(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
        if not self.tool_registry:
            self.refresh_tools()

        # Build system and user prompts
        prompts: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Track token, llm and took usage
        tokens_in = 0
        tokens_out = 0
        llm_count = 0
        tool_history: list[dict] = []

        # Load array of available tools
        tools = self.tools_payload()

        # Continue loop while we need to call the LLM:
        #   - Call LLM at least once
        #   - If LLM requests a tool call, we need to call LLM again:
        #       - To craft a final response
        #       - Or, determine if we need to call addt'l tools
        need_to_call_llm = True
        while need_to_call_llm and llm_count < 20:

            response = self.openai.chat.completions.create(
                model = self.model,
                messages = prompts,
                tools = tools,
                temperature = temperature
            )
            need_to_call_llm = False
            tokens_in += response.usage.prompt_tokens
            tokens_out += response.usage.completion_tokens
            llm_count += 1

            # Any functions / tools to call?
            tool_events: list[dict] = []
            tool_calls = response.choices[0].message.tool_calls
            if tool_calls is None:
                tool_calls = []
            for item in tool_calls:
                if item.type == "function":
                    need_to_call_llm = True
                    function_call_name = item.function.name
                    function_call_arguments = json.loads(item.function.arguments)
                    result = self._execute_tool_call(function_call_name, function_call_arguments)
                    print(f"Function: {function_call_name}, Args: {function_call_arguments}, Result: {result}")
                    prompts.append({
                        "role": "assistant",
                        "content": response.choices[0].message.content,
                        "tool_calls": [item]
                    })
                    prompts.append({
                        "role": "tool",
                        "tool_call_id": item.id,
                        "name": function_call_name,
                        "content": json.dumps(result)
                    })
                    tool_history.append({"name": function_call_name, "args": function_call_arguments, "result": result})

        return {
            "content": response.choices[0].message.content,
            "tool_history": tool_history,
            "usage_tokens_in": tokens_in,
            "usage_tokens_out": tokens_out,
            "llm_count": llm_count
        }
