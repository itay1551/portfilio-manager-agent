"""Verify VITE LLM vars are baked into the running UI container assets."""

from __future__ import annotations

import subprocess

import pytest

from .conftest import ROOT, load_llm_config


@pytest.mark.integration
@pytest.mark.local_only
def test_ui_assets_contain_llm_host():
    config = load_llm_config()
    if not config.llm_url:
        pytest.skip("OPENAI_API_ENDPOINT not set")

    llm_host = (
        config.llm_url.replace("https://", "").replace("http://", "").split("/")[0]
    )
    compose_file = ROOT / "deploy/local/compose.yml"
    cmd = [
        "podman",
        "compose",
        "-f",
        str(compose_file),
        "exec",
        "ui",
        "sh",
        "-c",
        f"grep -q '{llm_host}' /usr/share/nginx/html/assets/*.js",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        pytest.fail(
            f"LLM host '{llm_host}' not found in UI assets. "
            "Rebuild with: podman compose --env-file .env -f deploy/local/compose.yml up --build ui"
        )
