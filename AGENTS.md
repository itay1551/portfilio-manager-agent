# AGENTS.md

## Project Overview

This is the **Investment Advisor Agent** — a demo combining an LLM orchestrator with specialized financial tool agents.

**Stack:** Python 3.11/3.12, Flask, React + Vite, OpenAI SDK, scikit-learn, yfinance, Podman/Docker Compose, OpenShift/Knative.

---

## Architecture

```
┌─────────────┐     HTTP      ┌──────────────────┐     OpenAI API     ┌─────────┐
│  React UI   │──────────────▶│   Orchestrator   │───────────────────▶│   LLM   │
│  :8080      │               │   Flask :5000    │                    │(external)│
└─────────────┘               └────────┬─────────┘                    └─────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │  VaR Agent   │  │  Portfolio   │  │  Guidelines  │
            │  :7001       │  │  Agent :7002 │  │  Agent :7003 │
            └──────────────┘  └──────────────┘  └──────────────┘
```

**5 services**, all containerized:
- **UI** (`frontend/`) — React + Vite web app (nginx), port 8080
- **Orchestrator** (`orchestrator/src/`) — Flask API, port 5000
- **VaR Agent** (`tools/value_at_risk/src/`) — Flask, port 7001
- **Portfolio Agent** (`tools/portfolio/src/`) — Flask, port 7002
- **Guidelines Agent** (`tools/guidelines/src/`) — Flask, port 7003

---

## Directory Structure

```
├── frontend/                  # React + Vite UI (TypeScript, Vitest)
├── orchestrator/src/          # Flask orchestrator (app.py, orchestrator.py, pipeline.py)
├── tools/
│   ├── guidelines/            # PDF parsing + MLP prohibition classifier
│   │   ├── src/               # Flask app + Dockerfile
│   │   └── docs/              # Sample guideline PDFs
│   ├── portfolio/src/         # Random S&P 100 equal-weight portfolio builder
│   └── value_at_risk/src/     # Parametric 1-day VaR (app.py + portfolio.py, market_data.py, value_at_risk.py)
├── models/                    # Pre-trained MLP model (joblib)
├── deploy/
│   ├── local/                 # Local dev (compose.yml, podman scripts)
│   └── helm/                  # Helm chart (Chart.yaml, values.yaml, templates/)
├── build-script/              # Container image build script
├── images/                    # README screenshots
├── Makefile                   # deploy-local / deploy-cluster targets
├── .env.example               # Environment variable template
└── AGENTS.md                  # This file
```

---

## Two-Phase Design

### Phase 1 — Deterministic Pipeline

The orchestrator scripts tool calls in a fixed sequence (no LLM tool selection):

1. **Guidelines** → parse PDF, extract prohibited tickers via MLP + heuristics
2. **Portfolio** → build random equal-weight portfolio excluding prohibited symbols
3. **VaR** → calculate 1-day parametric VaR at 99% confidence
4. **Retry loop** → if VaR > max_var, regenerate portfolio (up to 10 attempts). The orchestrator implements this in `run_portfolio_var_loop` (monolithic `POST /pipeline`); the UI reimplements the same loop client-side when calling granular `/pipeline/*` endpoints.
5. **Email** → LLM drafts a client summary email (only LLM step in Phase 1)

### Phase 2 — Constrained Agentic Chat

The LLM can call only `portfolio_equities` and `value_at_risk` tools when `POST /chat` includes a `context` object (the normal UI path). Guidelines are NOT re-parseable — prohibited tickers persist in context. Max 20 LLM rounds per chat turn. Without `context`, legacy chat exposes all discovered tools.

---

## Tool Agent Contract

All tool agents implement the same HTTP interface:

- `GET /tools` — Returns OpenAI-style function definitions (name, description, JSON Schema parameters)
- `POST /tools/<tool_name>` — Execute tool with JSON body, returns JSON result

Tool names must be globally unique across all servers. The agentic `Orchestrator` class raises `ValueError` on duplicates during `refresh_tools()` and `refresh_tools_filtered()`; the deterministic pipeline's `_tool_servers()` silently keeps the last server for a duplicate name.

---

## Key Design Decisions

1. **No shared state between agents** — all context flows through the orchestrator via HTTP request/response
2. **LLM is external** — not containerized; endpoint/key/model passed per request from the UI
3. **Client-side pipeline orchestration** — the UI calls granular `/pipeline/*` endpoints for progress feedback rather than monolithic `/pipeline`
4. **Context as source of truth** — `pipeline_state["context"]` holds all portfolio state; chat mutations flow back via updated `context` in responses
5. **Tool discovery per request** — schemas are fetched fresh on each pipeline step invocation and each chat turn (no caching). A monolithic `POST /pipeline` may discover tools multiple times within one HTTP request.

---

## Running Locally

```bash
# Copy env template and configure LLM endpoint
cp .env.example .env

# Start all services
make deploy-local
# or: podman compose -f deploy/local/compose.yml up -d --build

# UI: http://localhost:8080
# Orchestrator API: http://localhost:5000
```

Environment variables:
- `OPENAI_API_ENDPOINT` — LLM base URL (include `/v1`)
- `OPENAI_API_TOKEN` — API key
- `OPENAI_MODEL` — Model name (e.g. `llama-3-3-70b-instruct-w8a8`)
- `ORCHESTRATOR_URL` — UI uses same-origin `/api/chat` by default; nginx in the UI container proxies `/api/*` to orchestrator. Override via `VITE_ORCHESTRATOR_URL` at build if needed.

---

## Coding Conventions

- **Python style:** Standard library imports first, then third-party, then local. No type stubs required.
- **Flask patterns:** All services use `app.run(host="0.0.0.0", port=int(os.getenv("PORT", default)))`. Only the orchestrator enables `flask-cors` globally; tool agents do not use CORS.
- **Error handling:** Pipeline functions raise `RuntimeError` on tool failures. Monolithic `POST /pipeline` maps those to HTTP 422; granular `/pipeline/*` endpoints return HTTP 500. Tool errors in agentic chat are returned as `{"error": "..."}` inline to the LLM.
- **Dependencies:** Orchestrator and tool agents each have a full `pip freeze` pin in `requirements.txt`. The UI uses `package.json` (React, Vite, Vitest). Orchestrator and tool agent Dockerfiles pre-install numpy/scipy/scikit-learn from wheels before `requirements.txt`.
- **Dockerfiles:** UI uses multi-stage `ubi9/nodejs-20` build + `ubi9/nginx-120` serve. Orchestrator and tool agents use `ubi10/python-312-minimal`, run as non-root user 1001, and pre-install numpy/scipy/scikit-learn from wheels.
- **Frontend tests:** Vitest + React Testing Library in `frontend/src/__tests__/`. Run with `npm test` in `frontend/`.
- **Service layout:** Portfolio and guidelines agents are single-file (`app.py`). VaR agent splits logic across `app.py`, `portfolio.py`, `market_data.py`, and `value_at_risk.py`. The orchestrator has three files (`app.py`, `orchestrator.py`, `pipeline.py`).

---

## Orchestrator API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/info` | GET | App metadata |
| `/pipeline` | POST | Full pipeline (monolithic) |
| `/pipeline/guidelines` | POST | Step 1: parse guidelines |
| `/pipeline/portfolio` | POST | Step 2: build portfolio |
| `/pipeline/var` | POST | Step 3: calculate VaR |
| `/pipeline/email` | POST | Step 4: draft email (requires LLM config) |
| `/chat` | POST | Phase 2 interactive chat |

All endpoints requiring LLM access expect a `config` object:
```json
{ "llmUrl": "https://...", "apiKey": "sk-...", "model": "model-name" }
```

---

## Common Development Tasks

### Adding a new tool agent

1. Create `tools/<name>/src/app.py` implementing `GET /tools` and `POST /tools/<tool_name>`
2. Add a `Dockerfile` and `requirements.txt` in the same directory
3. Add the service to `deploy/local/compose.yml` with a unique port
4. Add the URL to the orchestrator's `TOOL_SERVERS` environment variable
5. If the tool should be available in Phase 2 chat, add its name to `PHASE2_TOOLS` in `orchestrator/src/app.py`

### Modifying the pipeline

Edit `orchestrator/src/pipeline.py`. The pipeline is a linear sequence of function calls — add steps between existing ones or modify retry logic in `run_portfolio_var_loop`.

### Changing the UI

Edit `frontend/src/`. React components live in `components/`, pipeline logic in `hooks/usePipeline.ts`, API client in `api/client.ts`. Run locally with `npm run dev` in `frontend/` (port 8080). Tests: `npm test`.

### Building container images

```bash
./build-script/build_script.sh
```

Images are tagged for `quay.io/ikatav/portfolio-manager-agent:<service-name>`.

### Running tests

**CI (no live stack):**
- Frontend: `npm test` and `npm run build` in `frontend/`
- Python unit: `pytest tests/unit -m unit` (see `.github/workflows/test-python.yml`)
- Deploy manifests: `helm lint`, `helm template`, `podman compose config` (see `.github/workflows/test-deploy.yml`)

**Local unit tests:**

```bash
pip install -r tests/requirements.txt
pip install -r orchestrator/src/requirements.txt
pip install scikit-learn pdfminer.six joblib
make test-unit
```

**Local integration tests (stack must be running):**

```bash
make deploy-local   # terminal 1
make test-integration          # no LLM — health, proxy, granular pipeline, tools
make test-integration-llm      # includes full /pipeline and /chat (needs real .env)
```

Integration tests mirror [`.cursor/skills/verify-demo-stack/scripts/verify_ui_api_proxy.sh`](.cursor/skills/verify-demo-stack/scripts/verify_ui_api_proxy.sh) and [`verify_demo_stack.sh`](.cursor/skills/verify-demo-stack/scripts/verify_demo_stack.sh). They are **not** run in CI.

---

## Important File Relationships

- `orchestrator/src/app.py` → imports from `pipeline.py` and `orchestrator.py`
- `pipeline.py` → imports `HttpToolServer` from `orchestrator.py` (no circular dependency)
- `frontend/src/` → communicates with orchestrator over HTTP only (no shared code)
- `models/investment-guidelines-mlp.joblib` → mounted read-only into guidelines container at `/app/models`
- `tools/guidelines/docs/` → mounted read-only into guidelines container at `/app/docs`

---

## Known Issues / Inconsistencies

- Project folder name has a typo: `ai-portfilio-manager` (should be "portfolio")
- README references `build/` but actual path is `build-script/`; also references `build/deploy_podman.sh` but the script lives at `deploy/local/deploy_podman.sh`
- `deploy/local/deploy_podman_multi.sh` creates network `agentic-ai` but references `ai-network`
- Tool agent `requirements.txt` files contain many unused transitive dependencies (full pip freeze)
- UI has Vitest unit tests; Python has pytest unit tests in `tests/unit/`; integration tests in `tests/integration/` are local-only
