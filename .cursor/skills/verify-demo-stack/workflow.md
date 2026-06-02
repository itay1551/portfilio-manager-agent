# Verify Demo Stack — Manual Workflow

Use this when `scripts/verify_demo_stack.sh` fails or you need UI-level checks the script does not cover.

## Prerequisites

1. Project root (`deploy/local/compose.yml` present).
2. `.env` with real `OPENAI_API_ENDPOINT`, `OPENAI_API_TOKEN`, `OPENAI_MODEL`.
3. `podman compose`, `curl`, `jq`.

## Checklist

```
Verify demo stack (manual):
- [ ] 1. Build and start services
- [ ] 2. Wait for services healthy
- [ ] 3. Smoke-check HTTP endpoints
- [ ] 3b. UI /api proxy (verify_ui_api_proxy.sh)
- [ ] 4. Run pipeline (UI preferred)
- [ ] 5. Phase 2 chat — reject one holding
- [ ] 6. Read logs for all services
- [ ] 7. Validate results are logical
- [ ] 8. Report pass/fail
```

### 1. Build and start

```bash
cd <project-root>
podman compose --env-file .env -f deploy/local/compose.yml up -d --build
# or: make deploy-local
```

### 2. Services healthy

```bash
podman compose -f deploy/local/compose.yml ps
curl -sf http://localhost:5000/health
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8080/
```

All of `ui`, `orchestrator`, `risk`, `portfolio`, `guidelines` must be **running**.

### 3b. UI /api proxy (automated)

```bash
./.cursor/skills/verify-demo-stack/scripts/verify_ui_api_proxy.sh
```

Must print `PASS: UI /api proxy verification`. If this fails but `curl http://localhost:5000/health` works, rebuild the UI container (nginx had a stale orchestrator IP).

### 3. Tool discovery

```bash
curl -sf http://localhost:7001/tools | head -c 200
curl -sf http://localhost:7002/tools | head -c 200
curl -sf http://localhost:7003/tools | head -c 200
```

### 4. Run pipeline (UI)

1. Open http://localhost:8080
2. Confirm **Connection settings** (LLM URL, key, model) if `.env` not loaded in container
3. Defaults: guidelines CloudFront PDF, portfolio `1000000`, symbols `5`, max VaR `35000`
4. **Run pipeline** → progress ends with **Pipeline complete**
5. **Discuss your portfolio** unlocks; capture **Portfolio outputs**

6. In chat, send: *"I do not like [first symbol] in this portfolio. Please suggest a replacement and update the holdings."*
   - Assistant should name a replacement
   - **Portfolio outputs** panel updates (one symbol swapped, VaR recalculated)
   - Other four holdings unchanged

Re-run script only for API check:

```bash
SKIP_COMPOSE=1 ./.cursor/skills/verify-demo-stack/scripts/verify_demo_stack.sh
```

### 6. Logs

```bash
podman compose -f deploy/local/compose.yml logs --tail=300 ui orchestrator risk portfolio guidelines
```

**Fail** on tracebacks, `Tool not available`, `Connection refused`, or UI stuck on errors.

Narrow one service:

```bash
podman compose -f deploy/local/compose.yml logs --tail=150 <service-name>
```

### 7. Result validation

| Check | Expectation |
| --- | --- |
| Prohibited | List (may be empty); not error text |
| Portfolio | 5 rows with symbol, quantity, last_price |
| Exclusions | No holding symbol in prohibited list |
| VaR | > 0 and ≤ max_var ($35,000 default) |
| Draft email | English prose about portfolio/risk; not JSON/traceback |
| Chat | Interactive after success |
| Chat reject | One symbol swapped; VaR updates; 4/5 holdings kept |

**Red flags:** VaR $0 or over max without retries; empty portfolio + complete; `**Error:**` in progress log; chat changes all five holdings or leaves VaR stale.

### 8. Report template

```markdown
## Demo stack verification

**Status:** PASS | FAIL
**Compose:** [ok / issues]
**Services:** [all running / which failed]
**Pipeline:** [UI / API / script] — [complete / failed at step X]
**Results:** prohibited … | N positions … | VaR $… | email preview …
**Chat:** rejected … | kept 4/5 … | chat VaR $…
**Logs:** [clean / quote 1–2 error lines]
**Blockers:** [none / list]
```

Fix, then re-run script or repeat from step 1.

## Teardown

```bash
podman compose -f deploy/local/compose.yml down
```

## Reference

- Curl examples and service map: [reference.md](reference.md)
