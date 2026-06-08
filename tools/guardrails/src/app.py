"""Lightweight NeMo Guardrails validation service.

Wraps the nemoguardrails Python library and exposes a
/v1/guardrail/checks endpoint compatible with the OpenShift AI
NemoGuardrails microservice API.
"""

import os

from flask import Flask, request, jsonify
from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.rails.llm.options import RailStatus

app = Flask(__name__)

CONFIG_PATH = os.getenv("GUARDRAILS_CONFIG_PATH", "/config")
config = RailsConfig.from_path(CONFIG_PATH)
rails = LLMRails(config)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/v1/guardrail/checks", methods=["POST"])
def guardrail_checks():
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages", [])

    try:
        result = rails.check(messages=messages)
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 500

    if result.status == RailStatus.BLOCKED:
        rails_status = {}
        if result.rail:
            rails_status[result.rail] = {"status": "blocked"}
        return jsonify(
            {
                "status": "blocked",
                "rails_status": rails_status,
                "content": result.content or "",
            }
        ), 200

    return jsonify({"status": "success"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
