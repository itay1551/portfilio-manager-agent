#!/usr/bin/env bash
# End-to-end demo stack verification: compose, health, tools, pipeline, chat, logs.
# On failure, prints path to manual workflow (workflow.md).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKFLOW="$SKILL_DIR/workflow.md"

SERVICES=(ui orchestrator risk portfolio guidelines)
COMPOSE_WAIT_SEC="${COMPOSE_WAIT_SEC:-120}"
LOG_TAIL="${LOG_TAIL:-300}"

fail() {
  echo "" >&2
  echo "FAIL: $*" >&2
  echo "Manual fallback: $WORKFLOW" >&2
  exit 1
}

step() { echo "==> $*"; }

cd "$ROOT"
[[ -f deploy/local/compose.yml ]] || fail "run from project root (missing deploy/local/compose.yml)"

# --- Prerequisites ---
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  fail "missing $ENV_FILE — cp .env.example .env and set LLM vars"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for var in OPENAI_API_ENDPOINT OPENAI_API_TOKEN OPENAI_MODEL; do
  if [[ -z "${!var:-}" ]] || [[ "${!var}" == *"your-"* ]] || [[ "${!var}" == *"example.com"* ]]; then
    fail "set real values for $var in $ENV_FILE"
  fi
done

GUIDELINES_URL="${GUIDELINES_URL:-100}"
PORTFOLIO_VALUE="${PORTFOLIO_VALUE:-1000000}"
QTY_SYMBOLS="${QTY_SYMBOLS:-5}"
MAX_VAR="${MAX_VAR:-35000}"

command -v podman >/dev/null 2>&1 || fail "podman not found"
command -v curl >/dev/null 2>&1 || fail "curl not found"
command -v jq >/dev/null 2>&1 || fail "jq not found (dnf install jq / apt install jq)"

# --- 0. Frontend unit tests ---
if [[ "${SKIP_FRONTEND_TESTS:-0}" != "1" ]]; then
  if command -v npm >/dev/null 2>&1; then
    step "frontend unit tests (npm test)"
    (cd "$ROOT/frontend" && npm test) || fail "frontend unit tests failed"
  else
    step "npm not found — skipping frontend unit tests"
  fi
else
  step "SKIP_FRONTEND_TESTS=1 — skipping frontend unit tests"
fi

# --- 1. Compose ---
if [[ "${SKIP_COMPOSE:-0}" != "1" ]]; then
  step "podman compose up -d --build"
  podman compose --env-file "$ENV_FILE" -f deploy/local/compose.yml up -d --build
else
  step "SKIP_COMPOSE=1 — using existing containers"
fi

# --- 2. Wait for services (HTTP probes; avoids fragile compose JSON formats) ---
step "waiting for services (up to ${COMPOSE_WAIT_SEC}s)"
deadline=$((SECONDS + COMPOSE_WAIT_SEC))
ready=0
while (( SECONDS < deadline )); do
  if curl -sf http://localhost:5000/health >/dev/null 2>&1 \
    && curl -sf -o /dev/null http://localhost:8080/ 2>&1 \
    && curl -sf http://localhost:7001/tools >/dev/null 2>&1 \
    && curl -sf http://localhost:7002/tools >/dev/null 2>&1 \
    && curl -sf http://localhost:7003/tools >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

[[ "$ready" == "1" ]] || fail "services not healthy after ${COMPOSE_WAIT_SEC}s (check: podman compose ps)"
curl -sf http://localhost:5000/health | jq -e '.status == "ok"' >/dev/null \
  || fail "orchestrator health check failed"
if [[ "${SKIP_UI_PROXY:-0}" != "1" ]]; then
  export GUIDELINES_URL ENV_FILE UI_BASE ORCH_BASE CURL_MAX_TIME PORTFOLIO_VALUE QTY_SYMBOLS
  "$SCRIPT_DIR/verify_ui_api_proxy.sh" || fail "UI /api proxy verification failed (see verify_ui_api_proxy.sh)"
else
  step "SKIP_UI_PROXY=1 — skipping UI /api proxy verification"
  ui_code="$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8080/ || echo 000)"
  [[ "$ui_code" == "200" ]] || fail "UI returned HTTP $ui_code (expected 200)"
fi

# --- 3. Tool discovery ---
step "smoke-check tool /tools endpoints"
for port in 7001 7002 7003; do
  curl -sf "http://localhost:${port}/tools" | jq -e 'length > 0' >/dev/null \
    || fail "tool server on port $port unreachable or empty"
done
curl -sf http://localhost:7002/tools \
  | jq -e '[.[].name] | index("portfolio_replace_symbol") != null' >/dev/null \
  || fail "portfolio agent missing portfolio_replace_symbol tool"

# --- 4. Pipeline ---
step "POST /pipeline"
RESP="$(mktemp)"
trap 'rm -f "$RESP"' EXIT

HTTP_CODE="$(curl -s -w "%{http_code}" -o "$RESP" -X POST http://localhost:5000/pipeline \
  -H "Content-Type: application/json" \
  -d "{
    \"url_investment_guidelines\": \"$GUIDELINES_URL\",
    \"portfolio_value\": $PORTFOLIO_VALUE,
    \"qty_symbols\": $QTY_SYMBOLS,
    \"max_var\": $MAX_VAR,
    \"config\": {
      \"llmUrl\": \"$OPENAI_API_ENDPOINT\",
      \"apiKey\": \"$OPENAI_API_TOKEN\",
      \"model\": \"$OPENAI_MODEL\"
    }
  }")"

[[ "$HTTP_CODE" == "200" ]] || fail "pipeline HTTP $HTTP_CODE — $(cat "$RESP")"
jq -e '.error | not' "$RESP" >/dev/null 2>&1 || fail "pipeline error: $(jq -r '.error' "$RESP")"

PORTFOLIO_LEN="$(jq '.portfolio | length' "$RESP")"
VAR="$(jq '.valueAtRisk' "$RESP")"
EMAIL_LEN="$(jq '.draft_email | length' "$RESP")"
PROHIBITED="$(jq -c '.prohibited_tickers' "$RESP")"

[[ "$PORTFOLIO_LEN" == "$QTY_SYMBOLS" ]] \
  || fail "expected $QTY_SYMBOLS positions, got $PORTFOLIO_LEN"
awk -v v="$VAR" -v max="$MAX_VAR" 'BEGIN { exit !(v > 0 && v <= max) }' \
  || fail "valueAtRisk=$VAR (expected 0 < VaR <= $MAX_VAR)"
[[ "$EMAIL_LEN" -ge 50 ]] || fail "draft_email too short ($EMAIL_LEN chars)"

# Exclusion: no holding in prohibited list
overlap="$(jq -r --argjson n "$QTY_SYMBOLS" '
  [.portfolio[].symbol] as $hold |
  [.prohibited_tickers[]?] as $ban |
  [$hold[] | select(. as $s | $ban | index($s))] | unique | join(",")
' "$RESP")"
[[ -z "$overlap" ]] || fail "holdings overlap prohibited tickers: $overlap"

email_preview="$(jq -r '.draft_email | .[0:120]' "$RESP")"
if [[ "$email_preview" =~ ^(\{|\[|Traceback|Error) ]]; then
  fail "draft_email looks like JSON/error, not prose"
fi

PIPELINE_CTX="$(jq -c '.context' "$RESP")"
VAR_BEFORE="$VAR"
DISLIKE_SYMBOL="$(jq -r '.portfolio[0].symbol' "$RESP")"

# --- 5. Phase 2 chat: reject one holding ---
if [[ "${SKIP_CHAT:-0}" != "1" ]]; then
  step "POST /chat — reject holding ${DISLIKE_SYMBOL}"
  CHAT_RESP="$(mktemp)"
  CHAT_PAYLOAD="$(mktemp)"
  trap 'rm -f "$RESP" "$CHAT_RESP" "$CHAT_PAYLOAD"' EXIT

  jq -n \
    --argjson ctx "$PIPELINE_CTX" \
    --arg sym "$DISLIKE_SYMBOL" \
    --arg url "$OPENAI_API_ENDPOINT" \
    --arg key "$OPENAI_API_TOKEN" \
    --arg model "$OPENAI_MODEL" \
    '{
      message: ("I do not like \($sym) in this portfolio. Please suggest a replacement and update the holdings."),
      history: [],
      context: $ctx,
      config: {llmUrl: $url, apiKey: $key, model: $model}
    }' >"$CHAT_PAYLOAD"

  CHAT_HTTP="$(curl -s -w "%{http_code}" -o "$CHAT_RESP" -X POST http://localhost:5000/chat \
    -H "Content-Type: application/json" \
    -d @"$CHAT_PAYLOAD")"

  [[ "$CHAT_HTTP" == "200" ]] || fail "chat HTTP $CHAT_HTTP — $(cat "$CHAT_RESP")"
  jq -e '.error | not' "$CHAT_RESP" >/dev/null 2>&1 \
    || fail "chat error: $(jq -r '.error' "$CHAT_RESP")"

  CHAT_REPLY_LEN="$(jq '.content | length' "$CHAT_RESP")"
  [[ "$CHAT_REPLY_LEN" -ge 30 ]] || fail "chat reply too short ($CHAT_REPLY_LEN chars)"

  CHAT_VAR="$(jq '.context.valueAtRisk' "$CHAT_RESP")"
  CHAT_LEN="$(jq '.context.portfolio | length' "$CHAT_RESP")"
  CHAT_TOOLS="$(jq -r '[.tool_history[]?.name] | join(",")' "$CHAT_RESP")"
  CHAT_SYMBOLS="$(jq -r '[.context.portfolio[] | "\(.symbol)(\(.quantity))"] | join(", ")' "$CHAT_RESP")"
  CHAT_REPLY_PREVIEW="$(jq -r '.content | .[0:120]' "$CHAT_RESP")"

  [[ "$CHAT_LEN" == "$QTY_SYMBOLS" ]] \
    || fail "chat portfolio length $CHAT_LEN (expected $QTY_SYMBOLS)"

  awk -v v="$CHAT_VAR" -v before="$VAR_BEFORE" 'BEGIN { exit !(v > 0 && v != before) }' \
    || fail "chat valueAtRisk=$CHAT_VAR (expected > 0 and != pipeline VaR $VAR_BEFORE)"

  jq -e --arg sym "$DISLIKE_SYMBOL" '
    [.context.portfolio[].symbol] | index($sym) == null
  ' "$CHAT_RESP" >/dev/null \
    || fail "chat portfolio still contains rejected symbol $DISLIKE_SYMBOL"

  jq -e --arg sym "$DISLIKE_SYMBOL" '
    [.tool_history[]?.name] | index("portfolio_replace_symbol") != null
  ' "$CHAT_RESP" >/dev/null \
    || fail "chat did not call portfolio_replace_symbol (tools: ${CHAT_TOOLS:-none})"

  chat_overlap="$(jq -r '
    [.context.portfolio[].symbol] as $hold |
    [.context.prohibited_tickers[]?] as $ban |
    [$hold[] | select(. as $s | $ban | index($s))] | unique | join(",")
  ' "$CHAT_RESP")"
  [[ -z "$chat_overlap" ]] || fail "chat holdings overlap prohibited tickers: $chat_overlap"

  KEPT_COUNT="$(jq -r --argjson before "$PIPELINE_CTX" '
    (.context.portfolio | map(.symbol)) as $after |
    ($before.portfolio | map(.symbol)) as $orig |
    [$orig[] | select(. as $s | ($after | index($s)))] | length
  ' "$CHAT_RESP")"
  [[ "$KEPT_COUNT" -ge $((QTY_SYMBOLS - 1)) ]] \
    || fail "chat replaced too many holdings (kept $KEPT_COUNT of $QTY_SYMBOLS)"

  rm -f "$CHAT_RESP" "$CHAT_PAYLOAD"
  trap 'rm -f "$RESP"' EXIT
else
  step "SKIP_CHAT=1 — skipping Phase 2 chat check"
  CHAT_VAR=""
  CHAT_SYMBOLS=""
  CHAT_REPLY_PREVIEW=""
  KEPT_COUNT=""
fi

# --- 6. Logs ---
step "scanning service logs (tail $LOG_TAIL)"
LOG_TMP="$(mktemp)"
  podman compose -f deploy/local/compose.yml logs --tail="$LOG_TAIL" ui orchestrator risk portfolio guidelines >"$LOG_TMP" 2>&1 || true
if grep -iE 'traceback|unhandled exception' "$LOG_TMP" | grep -v 'Schema:' | head -1 | grep -q .; then
  grep -iE 'traceback|unhandled exception' "$LOG_TMP" | head -3 >&2
  fail "tracebacks in service logs"
fi
if grep -iE 'tool discovery failed|tool not available|connection refused' "$LOG_TMP" | head -1 | grep -q .; then
  grep -iE 'tool discovery failed|tool not available|connection refused' "$LOG_TMP" | head -3 >&2
  fail "tool/connectivity errors in logs"
fi
rm -f "$LOG_TMP"

# --- 7. Report ---
SYMBOLS="$(jq -r '[.portfolio[] | "\(.symbol)(\(.quantity))"] | join(", ")' "$RESP")"
echo ""
echo "PASS: demo stack verification"
echo "  services:     ${SERVICES[*]}"
echo "  prohibited:   $PROHIBITED"
echo "  positions:    $PORTFOLIO_LEN — $SYMBOLS"
echo "  valueAtRisk:  \$$VAR (max \$$MAX_VAR)"
echo "  draft_email:  ${EMAIL_LEN} chars — ${email_preview}..."
if [[ "${SKIP_CHAT:-0}" != "1" ]]; then
  echo "  chat:         rejected $DISLIKE_SYMBOL → kept $KEPT_COUNT/$QTY_SYMBOLS — $CHAT_SYMBOLS"
  echo "  chat VaR:     \$$CHAT_VAR (was \$$VAR_BEFORE)"
  echo "  chat reply:   ${CHAT_REPLY_PREVIEW}..."
fi
echo "  UI:           http://localhost:8080"
exit 0
