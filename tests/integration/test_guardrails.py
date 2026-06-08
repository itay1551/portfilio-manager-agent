"""NeMo Guardrails integration tests."""

from __future__ import annotations

import json
import os
import subprocess

import httpx
import pytest

from .conftest import GUARDRAILS_BASE, ORCH_BASE, LlmConfig

NAMESPACE = os.getenv("NAMESPACE", "investment-advisor-agent-itay")


def _oc(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["oc", *args], capture_output=True, text=True)


# ---- Cluster-only: deployment verification ----


@pytest.mark.integration
@pytest.mark.cluster_only
def test_guardrails_configmap_exists():
    """ConfigMap guardrails-config must exist with all config files."""
    result = _oc(
        "get",
        "configmap",
        "guardrails-config",
        "-n",
        NAMESPACE,
        "-o",
        "jsonpath={.data}",
    )
    assert result.returncode == 0, (
        f"ConfigMap guardrails-config not found: {result.stderr.strip()}"
    )
    data = json.loads(result.stdout)
    for key in ("config.yaml", "rails.co", "actions.py"):
        assert key in data, f"Missing key '{key}' in guardrails-config ConfigMap"
        assert len(data[key]) > 0, (
            f"Key '{key}' is empty in guardrails-config ConfigMap"
        )


@pytest.mark.integration
@pytest.mark.cluster_only
def test_nemoguardrails_ready():
    """NemoGuardrails CR must exist and report Ready."""
    result = _oc(
        "get",
        "nemoguardrails.trustyai.opendatahub.io/guardrails",
        "-n",
        NAMESPACE,
        "-o",
        "jsonpath={.status.phase}",
    )
    assert result.returncode == 0, (
        f"NemoGuardrails CR not found: {result.stderr.strip()}"
    )
    assert result.stdout.strip() == "Ready", (
        f"NemoGuardrails phase is '{result.stdout.strip()}', expected 'Ready'"
    )


@pytest.mark.integration
@pytest.mark.cluster_only
def test_guardrails_pod_running():
    """Guardrails pod must be Running with all containers ready."""
    result = _oc(
        "get",
        "pods",
        "-l",
        "app=guardrails",
        "-n",
        NAMESPACE,
        "-o",
        "jsonpath={.items[0].status.phase}",
    )
    assert result.returncode == 0 and result.stdout.strip() == "Running", (
        f"Guardrails pod not Running: phase={result.stdout.strip()}, err={result.stderr.strip()}"
    )
    ready = _oc(
        "get",
        "pods",
        "-l",
        "app=guardrails",
        "-n",
        NAMESPACE,
        "-o",
        "jsonpath={.items[0].status.containerStatuses[*].ready}",
    )
    for val in ready.stdout.split():
        assert val == "true", f"Not all guardrails containers are ready: {ready.stdout}"


@pytest.mark.integration
@pytest.mark.cluster_only
def test_guardrails_internal_service():
    """guardrails-internal Service must exist on port 8000."""
    result = _oc(
        "get",
        "svc",
        "guardrails-internal",
        "-n",
        NAMESPACE,
        "-o",
        "jsonpath={.spec.ports[0].port}",
    )
    assert result.returncode == 0, (
        f"guardrails-internal service not found: {result.stderr.strip()}"
    )
    assert result.stdout.strip() == "8000", (
        f"guardrails-internal port is {result.stdout.strip()}, expected 8000"
    )


@pytest.mark.integration
@pytest.mark.cluster_only
def test_orchestrator_has_guardrails_url():
    """Orchestrator deployment must have GUARDRAILS_URL pointing to the internal service."""
    result = _oc(
        "get",
        "deploy/orchestrator",
        "-n",
        NAMESPACE,
        "-o",
        "jsonpath={.spec.template.spec.containers[0].env}",
    )
    assert result.returncode == 0, result.stderr.strip()
    env_list = json.loads(result.stdout)
    gr_vars = [e for e in env_list if e["name"] == "GUARDRAILS_URL"]
    assert gr_vars, "GUARDRAILS_URL not set in orchestrator deployment"
    url = gr_vars[0]["value"]
    assert "guardrails-internal" in url, (
        f"GUARDRAILS_URL={url} does not point to guardrails-internal service"
    )
    assert ":8000" in url, f"GUARDRAILS_URL={url} does not target port 8000"


@pytest.mark.integration
@pytest.mark.cluster_only
def test_orchestrator_image_has_guardrails_module():
    """Orchestrator container must include guardrails.py (catches stale images)."""
    result = _oc(
        "exec",
        "deploy/orchestrator",
        "-n",
        NAMESPACE,
        "--",
        "python",
        "-c",
        "import guardrails; print(guardrails.GUARDRAILS_URL)",
    )
    assert result.returncode == 0, (
        f"guardrails module not importable in orchestrator: {result.stderr.strip()}"
    )
    assert "guardrails-internal" in result.stdout, (
        f"guardrails.GUARDRAILS_URL={result.stdout.strip()}, expected guardrails-internal URL"
    )


@pytest.mark.integration
@pytest.mark.cluster_only
def test_guardrails_reachable_from_orchestrator():
    """Orchestrator pod must be able to reach the guardrails service."""
    result = _oc(
        "exec",
        "deploy/orchestrator",
        "-n",
        NAMESPACE,
        "--",
        "python",
        "-c",
        "import requests; r = requests.get('http://guardrails-internal:8000/', timeout=5); "
        "print(r.status_code)",
    )
    assert result.returncode == 0, (
        f"Cannot reach guardrails from orchestrator: {result.stderr.strip()}"
    )
    assert result.stdout.strip() == "200", (
        f"Guardrails root returned {result.stdout.strip()}, expected 200"
    )


# ---- Direct guardrails endpoint tests (local only — cluster route requires auth) ----


@pytest.mark.integration
@pytest.mark.local_only
def test_guardrails_health(http_client: httpx.Client):
    """Guardrails service health endpoint returns 200."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set")
    resp = http_client.get(f"{GUARDRAILS_BASE}/health")
    assert resp.status_code == 200


@pytest.mark.integration
@pytest.mark.local_only
def test_guardrails_safe_input(http_client: httpx.Client):
    """A clean financial question should pass all rails."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set")
    resp = http_client.post(
        f"{GUARDRAILS_BASE}/v1/guardrail/checks",
        json={
            "model": "test",
            "messages": [
                {"role": "user", "content": "What is the current VaR of my portfolio?"}
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"


@pytest.mark.integration
@pytest.mark.local_only
def test_guardrails_blocks_ssn(http_client: httpx.Client):
    """A message containing an SSN should be blocked."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set")
    resp = http_client.post(
        f"{GUARDRAILS_BASE}/v1/guardrail/checks",
        json={
            "model": "test",
            "messages": [{"role": "user", "content": "My SSN is 123-45-6789"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "blocked"


@pytest.mark.integration
@pytest.mark.local_only
def test_guardrails_blocks_credit_card(http_client: httpx.Client):
    """A message containing a credit card number should be blocked."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set")
    resp = http_client.post(
        f"{GUARDRAILS_BASE}/v1/guardrail/checks",
        json={
            "model": "test",
            "messages": [
                {"role": "user", "content": "My card number is 4111 1111 1111 1111"}
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "blocked"


@pytest.mark.integration
@pytest.mark.local_only
def test_guardrails_blocks_off_topic(http_client: httpx.Client):
    """An off-topic request should be blocked by the financial topic check."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set")
    resp = http_client.post(
        f"{GUARDRAILS_BASE}/v1/guardrail/checks",
        json={
            "model": "test",
            "messages": [
                {"role": "user", "content": "Write me a poem about the ocean"}
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "blocked"


# ---- Orchestrator-level guardrails enforcement ----


@pytest.mark.integration
def test_chat_blocked_by_guardrails_pii(http_client: httpx.Client):
    """Chat endpoint should return 422 when user sends PII."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set (orchestrator has no GUARDRAILS_URL)")
    resp = http_client.post(
        f"{ORCH_BASE}/chat",
        json={
            "message": "My SSN is 123-45-6789, please update my account",
            "config": {
                "llmUrl": "http://fake:8080/v1",
                "apiKey": "fake",
                "model": "fake",
            },
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert "guardrails" in body["error"].lower() or "blocked" in body["error"].lower()


@pytest.mark.integration
def test_chat_blocked_by_guardrails_off_topic(http_client: httpx.Client):
    """Chat endpoint should return 422 for off-topic requests."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set (orchestrator has no GUARDRAILS_URL)")
    resp = http_client.post(
        f"{ORCH_BASE}/chat",
        json={
            "message": "Tell me a joke about cats",
            "config": {
                "llmUrl": "http://fake:8080/v1",
                "apiKey": "fake",
                "model": "fake",
            },
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body


@pytest.mark.integration
@pytest.mark.llm
def test_chat_safe_message_passes_guardrails(
    http_client: httpx.Client, llm_config: LlmConfig
):
    """A safe financial question should pass guardrails and return an LLM response."""
    if not GUARDRAILS_BASE:
        pytest.skip("GUARDRAILS_BASE not set")
    resp = http_client.post(
        f"{ORCH_BASE}/chat",
        json={
            "message": "What does Value at Risk mean?",
            "config": llm_config.as_payload(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body.get("content", "")) > 10
