# Verify Local Deployment — Reference

**Primary:** `./.cursor/skills/verify-local/scripts/verify_demo_stack.sh`  
**UI proxy only:** `./.cursor/skills/verify-local/scripts/verify_ui_api_proxy.sh`  
**Browser UI:** [browser-mcp.md](../browser-mcp.md) (chrome-devtools MCP, after scripts PASS)  
**Manual fallback:** [workflow.md](workflow.md)

## Service map (Podman Compose)

| Service | Port | Role |
| --- | --- | --- |
| ui | 8080 | React + Vite frontend (nginx) |
| orchestrator | 5000 | Pipeline + chat API |
| risk | 7001 | `value_at_risk` tool |
| portfolio | 7002 | `portfolio_equities`, `portfolio_replace_symbol` tools |
| guidelines | 7003 | `prohibited_symbols` tool |

Internal DNS: orchestrator reaches tools at `http://risk:7001`, etc. (see `deploy/local/compose.yml` `TOOL_SERVERS`).

## UI /api proxy (browser + granular pipeline)

The UI defaults to **Orchestrator URL** `/api/chat`. Nginx strips `/api` and forwards to `http://orchestrator:5000/…`.

| Browser / UI call | Proxied to |
| --- | --- |
| `GET http://localhost:8080/api/health` | `GET http://orchestrator:5000/health` |
| `POST http://localhost:8080/api/pipeline/guidelines` | `POST http://orchestrator:5000/pipeline/guidelines` |
| `POST http://localhost:8080/api/pipeline/portfolio` | `POST http://orchestrator:5000/pipeline/portfolio` |
| `POST http://localhost:8080/api/pipeline/var` | `POST http://orchestrator:5000/pipeline/var` |
| `POST http://localhost:8080/api/pipeline/email` | `POST http://orchestrator:5000/pipeline/email` |
| `POST http://localhost:8080/api/chat` | `POST http://orchestrator:5000/chat` |

Run the dedicated check:

```bash
./.cursor/skills/verify-local/scripts/verify_ui_api_proxy.sh
```

Success: script prints `PASS: UI /api proxy verification` with guidelines, portfolio, var, and LLM host in built JS.

**Note:** `verify_demo_stack.sh` runs this unless `SKIP_UI_PROXY=1`. Monolithic `POST :5000/pipeline` can pass while the UI granular path fails.

**Compose:** always pass `.env` for UI build args: `podman compose --env-file .env -f deploy/local/compose.yml up --build` (same as `make deploy-local`).

## Default pipeline inputs

Use local guidelines client **`100`** (mounted at `docs/client-100/investment-guidelines.pdf`):

```json
{
  "url_investment_guidelines": "100",
  "portfolio_value": 1000000,
  "qty_symbols": 5,
  "max_var": 35000
}
```

## Full pipeline API (alternative to UI steps)

Load `.env` then:

```bash
set -a && source .env && set +a

curl -sf -X POST http://localhost:5000/pipeline \
  -H "Content-Type: application/json" \
  -d "{
    \"url_investment_guidelines\": \"100\",
    \"portfolio_value\": 1000000,
    \"qty_symbols\": 5,
    \"max_var\": 35000,
    \"config\": {
      \"llmUrl\": \"${OPENAI_API_ENDPOINT}\",
      \"apiKey\": \"${OPENAI_API_TOKEN}\",
      \"model\": \"${OPENAI_MODEL}\"
    }
  }" | jq .
```

Success: HTTP 200, JSON with `portfolio` (array length 5), `valueAtRisk` ≤ 35000, non-empty `draft_email`, no top-level `error`.

## Phase 2 chat — reject one holding (mirrors script step 6)

After a successful pipeline, send a dislike message for the first holding:

```bash
CTX=$(curl -sf -X POST http://localhost:5000/pipeline ... | jq -c '.context')
DISLIKE=$(echo "$CTX" | jq -r '.portfolio[0].symbol')

curl -sf -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d "$(jq -n --argjson ctx "$CTX" --arg sym "$DISLIKE" \
    --arg url "$OPENAI_API_ENDPOINT" --arg key "$OPENAI_API_TOKEN" --arg model "$OPENAI_MODEL" \
    '{
      message: ("I do not like \($sym) in this portfolio. Please suggest a replacement and update the holdings."),
      history: [],
      context: $ctx,
      config: {llmUrl: $url, apiKey: $key, model: $model}
    }')" | jq .
```

Success:

- HTTP 200, non-empty `content`
- `tool_history` includes `portfolio_replace_symbol`
- Rejected symbol absent from `context.portfolio`
- `context.valueAtRisk` changed from pipeline VaR
- At least 4 of 5 original symbols still present
- No overlap between `context.portfolio` and `context.prohibited_tickers`

## Stepwise API (mirrors UI generator)

Same order as UI progress log. From the host through nginx (what the UI uses):

```bash
curl -sf http://localhost:8080/api/pipeline/guidelines \
  -H "Content-Type: application/json" \
  -d '{"url_investment_guidelines":"https://d15bgksgja6rr0.cloudfront.net/Neurosymbolic-Inc-Investment-Guidelines.pdf"}' \
  | jq '.prohibited_tickers'
```

Direct orchestrator (bypasses UI nginx):

1. `POST http://localhost:5000/pipeline/guidelines` — `url_investment_guidelines`
2. `POST /pipeline/portfolio` — `portfolio_value`, `qty_symbols`, `prohibited_tickers`
3. `POST /pipeline/var` — `portfolio`
4. Retry portfolio/var if VaR > max_var (up to 10 attempts)
5. `POST /pipeline/email` — `portfolio`, `valueAtRisk`, `config`

## Log grep shortcuts

```bash
podman compose -f deploy/local/compose.yml logs orchestrator 2>&1 | rg -i 'error|traceback|failed|exception' || true
podman compose -f deploy/local/compose.yml logs guidelines 2>&1 | rg -i 'error|traceback|failed' || true
podman compose -f deploy/local/compose.yml logs portfolio 2>&1 | rg -i 'error|traceback|failed' || true
podman compose -f deploy/local/compose.yml logs risk 2>&1 | rg -i 'error|traceback|failed' || true
podman compose -f deploy/local/compose.yml logs ui 2>&1 | rg -i 'error|traceback|failed' || true
```

## Common failures

| Symptom | Likely cause |
| --- | --- |
| Email step error | Invalid/missing LLM in `.env` |
| Guidelines fail | PDF URL unreachable or guidelines model/volume missing (`../../models`, `../../tools/guidelines/docs` relative to compose) |
| VaR retries exhausted | Random portfolio keeps exceeding max_var (re-run once; persistent → investigate risk tool) |
| Tool not available | `TOOL_SERVERS` mismatch or tool container not up |
| UI **Prohibited tickers Failed.** | `POST /api/pipeline/guidelines` failed — run `verify_ui_api_proxy.sh`; **502** = nginx stale orchestrator IP after recreate → `podman compose -f deploy/local/compose.yml up -d --build ui` |
| UI cannot reach orchestrator | Wrong orchestrator URL in Connection settings; or nginx 502 (see above). Workaround: `http://localhost:5000/chat` |
| Chat VaR unchanged | Orchestrator auto-VaR after portfolio change broken, or LLM skipped `portfolio_replace_symbol` |
| Chat replaced all holdings | LLM called `portfolio_equities` instead of `portfolio_replace_symbol` — check `PHASE2_SYSTEM` |

## Guidelines model volume

`deploy/local/compose.yml` mounts:

- `../../models` → guidelines ML model
- `../../tools/guidelines/docs` → docs

If guidelines container errors on startup, confirm these paths exist on the host before blaming application code.
