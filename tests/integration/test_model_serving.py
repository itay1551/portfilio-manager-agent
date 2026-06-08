"""Tests for the KServe InferenceService model serving setup."""

from __future__ import annotations

import os
import subprocess

import httpx
import pytest

from .conftest import ORCH_BASE, UI_API_BASE, post_json

NAMESPACE = os.getenv("NAMESPACE", "investment-advisor-agent-itay")


@pytest.mark.integration
@pytest.mark.cluster_only
def test_inferenceservice_ready():
    """InferenceService guidelines-mlp must report Ready on the cluster."""
    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=condition=Ready",
            "isvc/guidelines-mlp",
            "-n",
            NAMESPACE,
            "--timeout=10s",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"InferenceService not Ready: {result.stderr.strip()}"
    )


@pytest.mark.integration
@pytest.mark.cluster_only
def test_model_upload_job_completed():
    """The model-upload Job must have succeeded (or been TTL-cleaned after success)."""
    result = subprocess.run(
        [
            "oc",
            "get",
            "job/model-upload",
            "-n",
            NAMESPACE,
            "-o",
            "jsonpath={.status.succeeded}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "NotFound" in result.stderr:
        isvc = subprocess.run(
            [
                "oc",
                "wait",
                "--for=condition=Ready",
                "isvc/guidelines-mlp",
                "-n",
                NAMESPACE,
                "--timeout=10s",
            ],
            capture_output=True,
            text=True,
        )
        assert isvc.returncode == 0, (
            "model-upload Job not found and InferenceService not Ready — "
            f"upload likely failed: {isvc.stderr.strip()}"
        )
        return
    assert result.stdout.strip() == "1", (
        f"model-upload Job not succeeded: {result.stdout.strip()}"
    )


@pytest.mark.integration
def test_guidelines_pipeline_with_model_serving(
    http_client: httpx.Client, guidelines_payload: dict[str, str]
):
    """Pipeline guidelines step must return valid tickers via the model serving backend."""
    resp = post_json(
        http_client,
        f"{UI_API_BASE}/pipeline/guidelines",
        guidelines_payload,
    ).json()
    assert "prohibited_tickers" in resp
    assert isinstance(resp["prohibited_tickers"], list)
    assert len(resp["prohibited_tickers"]) > 0


@pytest.mark.integration
def test_guidelines_direct_orchestrator_with_model_serving(
    http_client: httpx.Client, guidelines_payload: dict[str, str]
):
    """Direct orchestrator guidelines call must succeed with model serving."""
    resp = post_json(
        http_client,
        f"{ORCH_BASE}/pipeline/guidelines",
        guidelines_payload,
    ).json()
    assert "prohibited_tickers" in resp
    assert len(resp["prohibited_tickers"]) > 0
    raw = resp.get("guidelines_raw", resp)
    assert raw.get("meta", {}).get("num_matches", 0) > 0
