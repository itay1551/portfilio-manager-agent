# Import necessary libraries
import time
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from openai import OpenAI
from orchestrator import Orchestrator, HttpToolServer
from pipeline import (
    ToolRegistry,
    parse_guidelines,
    build_portfolio,
    calculate_var,
    generate_draft_email,
    run_pipeline,
    build_context_from_pipeline,
    apply_phase2_tool_result,
    apply_symbol_rejection,
    disliked_symbol_in_message,
    should_regenerate_email,
    MAX_PORTFOLIO_ATTEMPTS,
)
import os

# Initialize the Flask application and enable CORS
app = Flask(__name__)
CORS(app)

TOOL_SERVERS = [
    u.strip()
    for u in os.getenv(
        "TOOL_SERVERS",
        "http://localhost:7001,http://localhost:7002,http://localhost:7003",
    ).split(",")
    if u.strip()
]

PHASE2_TOOLS = {"portfolio_equities", "portfolio_replace_symbol", "value_at_risk"}

PHASE2_SYSTEM = (
    "You are a friendly portfolio manager assistant helping a client review their "
    "holdings. The user is reviewing a generated portfolio. "
    "Answer questions using the portfolio context provided. "
    "When the user rejects one specific ticker, call portfolio_replace_symbol with that "
    "remove_symbol, the current portfolio, portfolio_value from context inputs, and "
    "symbols_exclusion from prohibited_tickers. Keep all other holdings unchanged. "
    "When the user asks for a broader rebuild, call portfolio_equities instead "
    "(symbols_exclusion must include prohibited_tickers). "
    "Do not re-parse guidelines. max_var does not apply in this phase. "
    "After any portfolio change, briefly summarize what changed in plain English "
    "(e.g. which symbol was swapped and the new 1-day VaR as a dollar amount). "
    "Do not regenerate the draft client email unless the user explicitly asks. "
    "Response style: write conversational prose only, as if speaking to the client. "
    "Never paste JSON, code blocks, tool payloads, field names, or structured data "
    "in your reply. Do not echo the context object or tool results verbatim. "
    "The UI already shows the full portfolio table and outputs — keep chat answers "
    "short, clear, and human-readable."
)


def get_tool_servers() -> list[HttpToolServer]:
    return [HttpToolServer(u) for u in TOOL_SERVERS]


def get_tool_registry() -> ToolRegistry:
    """Discover tools once per HTTP request."""
    registry = g.get("tool_registry")
    if registry is None:
        registry = ToolRegistry(get_tool_servers())
        g.tool_registry = registry
    return registry


def parse_llm_config(payload: dict) -> tuple[OpenAI, str] | tuple[None, str]:
    config = payload.get("config") or {}
    llm_base_url = config.get("llmUrl") or config.get("llm_url")
    llm_model = config.get("model")
    llm_api_key = config.get("apiKey") or config.get("api_key")
    if not llm_base_url or not llm_model or not llm_api_key:
        return None, "config.llmUrl, config.model, and config.apiKey are required"
    client = OpenAI(base_url=llm_base_url, api_key=llm_api_key)
    return client, llm_model


def pipeline_error_response(exc: Exception):
    if isinstance(exc, RuntimeError):
        return jsonify({"error": str(exc)}), 422
    return jsonify({"error": str(exc)}), 500


# Health endpoint
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# Info endpoint
@app.route("/info", methods=["GET"])
def info():
    return jsonify(
        {
            "app_name": "Investment Advisor Agent",
            "author": "Aric Rosenbaum",
            "version": "1.0.0",
            "max_portfolio_attempts": MAX_PORTFOLIO_ATTEMPTS,
        }
    ), 200


@app.route("/pipeline/guidelines", methods=["POST"])
def pipeline_guidelines():
    payload = request.get_json(silent=True) or {}
    url = payload.get("url_investment_guidelines")
    if not url:
        return jsonify({"error": "url_investment_guidelines is required"}), 400
    try:
        result = parse_guidelines(get_tool_registry(), url)
        return jsonify(result), 200
    except Exception as e:
        return pipeline_error_response(e)


@app.route("/pipeline/portfolio", methods=["POST"])
def pipeline_portfolio():
    payload = request.get_json(silent=True) or {}
    try:
        portfolio_value = int(payload.get("portfolio_value", 1_000_000))
        qty_symbols = int(payload.get("qty_symbols", 5))
        prohibited = payload.get("prohibited_tickers", [])
        portfolio = build_portfolio(
            get_tool_registry(),
            portfolio_value,
            qty_symbols,
            prohibited,
        )
        return jsonify({"portfolio": portfolio}), 200
    except Exception as e:
        return pipeline_error_response(e)


@app.route("/pipeline/var", methods=["POST"])
def pipeline_var():
    payload = request.get_json(silent=True) or {}
    portfolio = payload.get("portfolio")
    if not portfolio:
        return jsonify({"error": "portfolio is required"}), 400
    try:
        result = calculate_var(get_tool_registry(), portfolio)
        return jsonify(result), 200
    except Exception as e:
        return pipeline_error_response(e)


@app.route("/pipeline/email", methods=["POST"])
def pipeline_email():
    payload = request.get_json(silent=True) or {}
    llm_client, model_or_err = parse_llm_config(payload)
    if llm_client is None:
        return jsonify({"error": model_or_err}), 400
    portfolio = payload.get("portfolio")
    value_at_risk = payload.get("valueAtRisk")
    if portfolio is None or value_at_risk is None:
        return jsonify({"error": "portfolio and valueAtRisk are required"}), 400
    try:
        email = generate_draft_email(
            llm_client, model_or_err, portfolio, float(value_at_risk)
        )
        return jsonify({"draft_email": email}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/pipeline", methods=["POST"])
def pipeline():
    payload = request.get_json(silent=True) or {}
    url = payload.get("url_investment_guidelines")
    if not url:
        return jsonify({"error": "url_investment_guidelines is required"}), 400

    llm_client, model_or_err = parse_llm_config(payload)
    if llm_client is None:
        return jsonify({"error": model_or_err}), 400
    llm_model = model_or_err

    try:
        portfolio_value = int(payload.get("portfolio_value", 1_000_000))
        qty_symbols = int(payload.get("qty_symbols", 5))
        max_var = float(payload.get("max_var", 35_000))
        result = run_pipeline(
            get_tool_registry(),
            llm_client,
            llm_model,
            url,
            portfolio_value,
            qty_symbols,
            max_var,
        )
        result["context"] = build_context_from_pipeline(result)
        return jsonify(result), 200
    except Exception as e:
        return pipeline_error_response(e)


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user = payload.get("message")
    if not user:
        return jsonify({"error": "'message' is required"}), 400

    llm_client, model_or_err = parse_llm_config(payload)
    if llm_client is None:
        return jsonify({"error": model_or_err}), 400
    llm_model = model_or_err

    system = payload.get("system", PHASE2_SYSTEM)
    temperature = float(payload.get("temperature", 0.2))
    context = payload.get("context")
    history = payload.get("history") or []

    tool_servers = get_tool_servers()
    orchestrator = Orchestrator(llm_client, llm_model, tool_servers)
    registry = get_tool_registry()

    t0 = time.time()
    try:
        if context is not None:
            ctx = dict(context)
            messages = [
                m
                for m in history
                if m.get("role") in ("user", "assistant") and m.get("content")
            ]

            server_tool_history: list[dict] = []
            disliked = disliked_symbol_in_message(user, ctx.get("portfolio", []))
            if disliked:
                before = list(ctx.get("portfolio", []))
                ctx = apply_symbol_rejection(ctx, disliked, registry)
                server_tool_history.append(
                    {
                        "name": "portfolio_replace_symbol",
                        "args": {"remove_symbol": disliked, "portfolio": before},
                        "result": ctx.get("portfolio", []),
                    }
                )

            def on_tool(tool_name: str, result, args: dict) -> None:
                nonlocal ctx
                ctx = apply_phase2_tool_result(
                    ctx, tool_name, result, registry, tool_args=args
                )

            result = orchestrator.chat_with_context(
                system,
                messages + [{"role": "user", "content": user}],
                ctx,
                allowed_tools=PHASE2_TOOLS,
                temperature=temperature,
                on_tool_result=on_tool,
            )

            if should_regenerate_email(user):
                try:
                    ctx["draft_email"] = generate_draft_email(
                        llm_client,
                        llm_model,
                        ctx.get("portfolio", []),
                        float(ctx.get("valueAtRisk", 0)),
                    )
                except Exception as e:
                    app.logger.warning(f"Draft email regeneration failed: {e}")

            dt = time.time() - t0
            tool_history = server_tool_history + result["tool_history"]
            return jsonify(
                {
                    "content": result["content"],
                    "context": ctx,
                    "model": llm_model,
                    "tool_history": tool_history,
                    "latency_sec": round(dt, 3),
                    "usage_tokens_in": result["usage_tokens_in"],
                    "usage_tokens_out": result["usage_tokens_out"],
                    "llm_count": result["llm_count"],
                }
            ), 200

        # Legacy free-form agentic chat (all tools)
        orchestrator.refresh_tools()
        result = orchestrator.chat_agentic(system, user, temperature=temperature)
        dt = time.time() - t0
        return jsonify(
            {
                "content": result["content"],
                "model": llm_model,
                "tool_history": result["tool_history"],
                "latency_sec": round(dt, 3),
                "usage_tokens_in": result["usage_tokens_in"],
                "usage_tokens_out": result["usage_tokens_out"],
                "llm_count": result["llm_count"],
            }
        ), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---- Entrypoint ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
