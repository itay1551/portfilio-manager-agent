# Import necessary libraries
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
from openai import OpenAI
from orchestrator import Orchestrator, HttpToolServer
import os
import requests

# Initialize the Flask application and enable CORS
app = Flask(__name__)
CORS(app)

# Where do Tool Servers sit
TOOL_SERVERS = "http://localhost:7001, http://localhost:7002, http://localhost:7003".split(",")
#TOOL_SERVERS = "http://neurosymbolic-ai-risk:7001, http://neurosymbolic-ai-portfolio:7002, http://neurosymbolic-ai-guidelines:7003".split(",")

# Health endpoint
@app.route("/health", methods=['GET'])
def health():
    return jsonify({"status": 200}), 400


# Info endpoint
@app.route("/info", methods=['GET'])
def info():
    return jsonify({
        "app_name": "Neurosymbolic AI demo", 
        "author": "Aric Rosenbaum", 
        "version": "1.0.0"}), 400


# Chat endpoint        
@app.route("/chat", methods=['POST'])
def chat():
    
    """
    Body:
    {
        "system": "optional system prompt",
        "message": "user prompt (required)",
        "temperature": 0.2
    }
    """

    # Parse parms and default where needed
    payload = request.get_json(silent=True) or {}
    user = payload.get("message")
    if not user:
        return jsonify({"error": "'message' prompt is required"}), 400
    system = payload.get("system", "You are an MCP-style orchestrator. Use tools when useful.")
    temperature = float(payload.get("temperature", 0.2))
    llm_base_url = payload.get("config").get("llmUrl")
    if not user:
        return jsonify({"error": "'llm_base_url' prompt is required"}), 400
    llm_model = payload.get("config").get("model")
    if not llm_model:
        return jsonify({"error": "'llm_model' prompt is required"}), 400
    llm_api_key = payload.get("config").get("apiKey")
    if not llm_api_key:
        return jsonify({"error": "'llm_api_key' prompt is required"}), 400
    debug_mode = payload.get("config").get("debugMode")
    if not debug_mode:
        debug_mode = True

    # Init the LLM client.
    #  n.b. - While are using the OpenAI library, we could target any compatible LLM
    llm_client = OpenAI(
        base_url = llm_base_url,
        api_key = llm_api_key
    )

    # Init MCP style orchestrator client including tools
    print(f"Tool endpoints: {TOOL_SERVERS}")
    tool_servers = [HttpToolServer(u.strip()) for u in TOOL_SERVERS] 
    orchestrator = Orchestrator(llm_client, llm_model, tool_servers)

    try:
        orchestrator.refresh_tools()
    except Exception as e:
        app.logger.warning(f"Tool discovery failed at startup: {e}") 

    # Execute query
    t0 = time.time()
    try:
        result = orchestrator.chat_agentic(system, user, temperature = temperature)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    dt = time.time() - t0

    # Return
    #   n.b. - In prod, be careful with returning tool history since it could include PII
    content = result["content"]
    return jsonify({
        "content": content,
        "model": llm_model,
        "tool_history": result["tool_history"],
        "latency_sec": round(dt, 3),
        "usage_tokens_in": result["usage_tokens_in"],
        "usage_tokens_out": result["usage_tokens_out"],
        "llm_count": result["llm_count"]
    })


# ---- Entrypoint ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))  # run multiple servers by changing PORT
    # For local dev; use gunicorn/waitress for production
    app.run(host="0.0.0.0", port=port, debug=True)