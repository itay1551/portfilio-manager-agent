# Browser verification (Chrome DevTools MCP)

Use the **`chrome-devtools`** MCP server after API/script checks pass, or when the UI misbehaves but curls succeed.

**Config:** project `.cursor/mcp.json` (gitignored, local only). Requires Node 20+, Chrome, and MCP enabled in Cursor Settings.

**If MCP is unavailable:** fall back to [verify-local/workflow.md](verify-local/workflow.md) manual steps and note `Browser MCP: skipped (not connected)` in the report.

---

## Prerequisites

1. **Cursor MCP connected** — Settings → MCP → `chrome-devtools` shows tools (not error / empty).
2. **Stack reachable** — local `http://localhost:8080` or cluster UI route from `oc get route ui`.
3. **LLM config** — `.env` loaded into UI build (local) or cluster secret (cluster). Pipeline email + chat need a real model.

**Skip browser MCP:** set `SKIP_BROWSER_MCP=1` (scripts still run; MCP step omitted).

---

## Resolve UI URL

| Target | URL |
| --- | --- |
| Local (default) | `http://localhost:8080` |
| Local override | `$UI_BASE` env var |
| Cluster | `http://$(oc get route ui -n $NAMESPACE -o jsonpath='{.spec.host}')` |

---

## MCP workflow (local or cluster)

Run these steps with **chrome-devtools** MCP tools. Take a screenshot on any failure.

### 1. Open and baseline

1. Navigate to the UI URL.
2. Confirm the page loads (title/content visible, no blank screen).
3. Read **console** messages — report errors and failed network requests.

### 2. Connection settings

1. Open **Connection settings** (if collapsed).
2. Confirm **LLM URL**, **API key**, and **model** are populated (not empty placeholders).
3. Local: host should match `OPENAI_API_ENDPOINT` from `.env`.

### 3. Run pipeline (UI)

1. Set **Investment guidelines** to client **`100`** (local PDF; avoid CloudFront sample URLs — often 403).
2. Defaults: portfolio `1000000`, symbols `5`, max VaR `35000`.
3. Click **Run pipeline**.
4. Wait until progress shows **Pipeline complete** (not stuck on a step or `**Error:**`).
5. Confirm **Portfolio outputs** shows ~5 holdings with symbols and VaR > 0.

### 4. Phase 2 chat

1. Confirm **Discuss your portfolio** is enabled.
2. Send: *"I do not like [first symbol] in this portfolio. Please suggest a replacement and update the holdings."*
3. Expect: assistant names a replacement; **Portfolio outputs** updates (one symbol swapped, VaR recalculated); other four holdings unchanged.

### 5. Final checks

- No console errors during pipeline or chat.
- No hung `/api/*` requests (check network panel if progress stalls).
- Screenshot of final state (pipeline complete + chat response).

---

## Pass / fail criteria

| Check | Pass | Fail |
| --- | --- | --- |
| Page load | HTTP 200, UI renders | Blank page, 502, infinite spinner |
| Connection settings | LLM URL/key/model set | "Set LLM URL, API key, and model" |
| Pipeline | **Pipeline complete** | Stuck step, prohibited error, VaR $0 |
| Portfolio | 5 rows, no prohibited overlap | Empty portfolio, wrong count |
| Chat | 1 symbol swapped, VaR updated | Chat locked, all 5 changed, stale VaR |
| Console | No errors | JS errors, failed fetches |

---

## Report snippet (add to skill report)

```markdown
**Browser MCP:** PASS / FAIL / skipped
**URL:** [localhost:8080 | cluster route]
**Pipeline UI:** [complete | failed at step X]
**Chat:** [rejected SYMBOL → REPLACEMENT | not tested]
**Console:** [clean | errors: …]
**Screenshot:** [attached on failure]
```
