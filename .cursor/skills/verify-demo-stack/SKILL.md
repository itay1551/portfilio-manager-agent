---
name: verify
description: Verify the pipeline and frontend unit tests. Use after every code change of orchestrator/src/, tools/, frontend/, or deploy/local/compose.yml.
---

# Verify Demo Stack

## Default (always try first)

From project root:

```bash
./.cursor/skills/verify-demo-stack/scripts/verify_demo_stack.sh
```

Same stack as local dev:

```bash
make deploy-local   # podman compose --env-file .env -f deploy/local/compose.yml up --build
```

## UI /api proxy only (browser path)

When the UI shows **Prohibited tickers — Failed.**, **Set LLM URL…**, or requests hang on `:8080`:

```bash
./.cursor/skills/verify-demo-stack/scripts/verify_ui_api_proxy.sh
```

---

## Verification matrix (what PASS means)

| # | Check | How |
| --- | --- | --- |
| 0 | Frontend unit tests | `npm test` in `frontend/` |
| 1 | Compose + `.env` | `podman compose --env-file .env … up -d --build` — bakes `VITE_OPENAI_*` into UI |
| 2 | All services up | `:8080`, `:5000/health`, `:7001–7003/tools` |
| 3 | UI static + nginx proxy | `GET :8080/`, `GET :8080/api/health` |
| 4 | Guidelines direct vs UI | `POST :5000/pipeline/guidelines` and `POST :8080/api/pipeline/guidelines` — same `prohibited_tickers` |
| 5 | Granular UI pipeline | `POST :8080/api/pipeline/portfolio` then `POST :8080/api/pipeline/var` (same as browser) |
| 6 | UI LLM defaults baked | LLM host from `.env` present in `/usr/share/nginx/html/assets/*.js` |
| 7 | Tool agents | `/tools` on 7001–7003; `portfolio_replace_symbol` on 7002 |
| 8 | Full pipeline | `POST :5000/pipeline` — positions, VaR ≤ max, email, no prohibited overlap |
| 9 | Phase 2 chat | Reject first holding — `portfolio_replace_symbol`, updated VaR |
| 10 | Logs | No tracebacks / connection errors (current container session) |

Default guidelines input: client **`100`** (local PDF at `docs/client-100/`). CloudFront sample URLs often return **403**.

---

## What `verify_demo_stack.sh` does

0. **Frontend unit tests** — `npm test` in `frontend/` (skip with `SKIP_FRONTEND_TESTS=1`)
1. Requires `.env` with real `OPENAI_API_*` vars
2. **`podman compose --env-file .env up -d --build`** (skip with `SKIP_COMPOSE=1`)
3. Waits for all five services + orchestrator health
4. **`verify_ui_api_proxy.sh`** — full browser-path checks (skip with `SKIP_UI_PROXY=1`)
5. Smoke-tests `/tools` on 7001–7003
6. `POST /pipeline` on `:5000` — positions, VaR, email, exclusions
7. `POST /chat` — reject first holding (skip with `SKIP_CHAT=1`)
8. Scans logs for tracebacks and tool errors
9. Prints `PASS` summary or exits non-zero

**Requires:** `podman`, `curl`, `jq`.

## What `verify_ui_api_proxy.sh` does

1. `GET :8080/` — static UI
2. `GET :8080/api/health` — nginx → orchestrator (with timeout; catches hang)
3. `POST :5000/pipeline/guidelines` — direct orchestrator
4. `POST :8080/api/pipeline/guidelines` — must match step 3
5. `POST :8080/api/pipeline/portfolio` — granular step 2
6. `POST :8080/api/pipeline/var` — granular step 3
7. Grep UI `assets/*.js` for LLM host from `.env` (catches empty Connection settings)

---

## On script failure

1. Read the `FAIL:` line and log excerpt from the script output.
2. For UI issues, run `verify_ui_api_proxy.sh` first.
3. Open **[workflow.md](workflow.md)** for manual steps at http://localhost:8080
4. Use **[reference.md](reference.md)** for per-endpoint curls
5. Re-run until exit `0`

## Optional env vars

| Variable | Default | Effect |
| --- | --- | --- |
| `SKIP_FRONTEND_TESTS=1` | off | Skip `npm test` |
| `SKIP_COMPOSE=1` | off | Do not run compose up |
| `SKIP_UI_PROXY=1` | off | Skip `verify_ui_api_proxy.sh` |
| `SKIP_CHAT=1` | off | Skip Phase 2 chat |
| `COMPOSE_WAIT_SEC` | 120 | Max wait for healthy stack |
| `CURL_MAX_TIME` | 60 | Per-request timeout (UI proxy script) |
| `LOG_TAIL` | 300 | Log lines to scan |
| `ENV_FILE` | `.env` | LLM credentials + compose `--env-file` |
| `GUIDELINES_URL` | `100` | Client ID or URL for guidelines |
| `UI_BASE` | `http://localhost:8080` | UI base URL |
| `ORCH_BASE` | `http://localhost:5000` | Orchestrator base URL |
| `PORTFOLIO_VALUE` | `1000000` | Portfolio step input |
| `QTY_SYMBOLS` | `5` | Holdings count |

## Report (after PASS)

```markdown
## Demo stack verification

**Status:** PASS
**Method:** verify_demo_stack.sh (+ verify_ui_api_proxy.sh)
**UI proxy:** health ok; guidelines/portfolio/var via :8080/api; direct vs nginx match
**UI build:** LLM host baked from .env
**Pipeline:** [prohibited, positions, VaR, email preview]
**Chat:** [rejected symbol, kept N/5, chat VaR]
**Logs:** clean
**Blockers:** none
```

## Debugging UI / connectivity

```bash
# nginx vs orchestrator
curl -s --max-time 5 http://localhost:8080/api/health
curl -s --max-time 5 http://localhost:5000/health

# guidelines (local client)
curl -s -X POST http://localhost:8080/api/pipeline/guidelines \
  -H "Content-Type: application/json" \
  -d '{"url_investment_guidelines": "100"}' | jq .prohibited_tickers

# LLM vars in UI image
grep -o 'litellm[^"]*' frontend/dist/assets/*.js   # after npm run build
podman compose -f deploy/local/compose.yml exec ui \
  sh -c 'grep -o "litellm[^\"]*" /usr/share/nginx/html/assets/*.js | head -1'

# guidelines logs
podman compose -f deploy/local/compose.yml logs guidelines --tail=20
```

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Set LLM URL, API key, and model` | UI built without `.env` build args | `make deploy-local` or `podman compose --env-file .env … up -d --build ui` |
| `/api/*` hangs | nginx stale orchestrator IP | `podman compose restart ui` or full `make deploy-local` |
| Guidelines 500 | CloudFront 403 or wrong path | Use `GUIDELINES_URL=100`; path must be `docs/client-100/` in container |
| VaR 500 | yfinance MultiIndex | `multi_level_index=False` on `yf.download()` |
| No Python logs | Buffered stdout | `PYTHONUNBUFFERED=1` in compose |

## Teardown

Only when asked: `podman compose down`
