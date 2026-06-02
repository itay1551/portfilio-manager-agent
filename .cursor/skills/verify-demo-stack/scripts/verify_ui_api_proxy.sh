#!/usr/bin/env bash
# Verify UI path: static page, nginx /api/* proxy, granular pipeline steps (browser path),
# orchestrator direct comparison, and VITE LLM vars baked into the UI image.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() {
  echo "" >&2
  echo "FAIL: $*" >&2
  echo "Fix: make deploy-local  (uses podman compose --env-file .env)" >&2
  echo "Or: podman compose --env-file .env -f deploy/local/compose.yml up -d --build" >&2
  echo "If /api hangs after rebuilding orchestrator only: podman compose restart ui" >&2
  echo "Manual fallback: $SKILL_DIR/workflow.md" >&2
  exit 1
}

step() { echo "==> $*"; }

cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
GUIDELINES_URL="${GUIDELINES_URL:-100}"
UI_BASE="${UI_BASE:-http://localhost:8080}"
ORCH_BASE="${ORCH_BASE:-http://localhost:5000}"
CURL_MAX_TIME="${CURL_MAX_TIME:-60}"
PORTFOLIO_VALUE="${PORTFOLIO_VALUE:-1000000}"
QTY_SYMBOLS="${QTY_SYMBOLS:-5}"

command -v curl >/dev/null 2>&1 || fail "curl not found"
command -v jq >/dev/null 2>&1 || fail "jq not found"
command -v podman >/dev/null 2>&1 || fail "podman not found"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

curl_json() {
  local method="$1" url="$2" data="${3:-}"
  local out="$4"
  local code
  if [[ -n "$data" ]]; then
    code="$(curl -s --max-time "$CURL_MAX_TIME" -o "$out" -w "%{http_code}" -X "$method" "$url" \
      -H "Content-Type: application/json" -d "$data")"
  else
    code="$(curl -s --max-time "$CURL_MAX_TIME" -o "$out" -w "%{http_code}" -X "$method" "$url")"
  fi
  echo "$code"
}

# --- UI static + /api/health ---
step "UI static page ($UI_BASE)"
ui_code="$(curl -sf --max-time 10 -o /dev/null -w "%{http_code}" "$UI_BASE/" 2>/dev/null || echo 000)"
[[ "$ui_code" == "200" ]] || fail "UI returned HTTP $ui_code (expected 200)"

step "UI nginx GET $UI_BASE/api/health → orchestrator"
TMPFILES=()
tmpfile() { local f; f="$(mktemp)"; TMPFILES+=("$f"); echo "$f"; }
trap 'rm -f "${TMPFILES[@]}"' EXIT

health_tmp="$(tmpfile)"
health_code="$(curl_json GET "$UI_BASE/api/health" "" "$health_tmp")"
[[ "$health_code" == "200" ]] || fail "GET $UI_BASE/api/health HTTP $health_code (hang/502 → restart ui or full compose up)"
jq -e '.status == "ok"' "$health_tmp" >/dev/null \
  || fail "GET $UI_BASE/api/health body invalid — $(cat "$health_tmp")"

# --- Guidelines: direct orchestrator vs UI proxy (same payload) ---
step "POST $ORCH_BASE/pipeline/guidelines (direct orchestrator)"
guidelines_direct="$(tmpfile)"
guidelines_payload="{\"url_investment_guidelines\": \"$GUIDELINES_URL\"}"
direct_code="$(curl_json POST "$ORCH_BASE/pipeline/guidelines" "$guidelines_payload" "$guidelines_direct")"
[[ "$direct_code" == "200" ]] \
  || fail "POST $ORCH_BASE/pipeline/guidelines HTTP $direct_code — $(head -c 300 "$guidelines_direct")"
jq -e '.prohibited_tickers | length >= 0' "$guidelines_direct" >/dev/null \
  || fail "direct guidelines missing prohibited_tickers"
prohibited_direct="$(jq -c '.prohibited_tickers' "$guidelines_direct")"

step "POST $UI_BASE/api/pipeline/guidelines (browser path via nginx)"
guidelines_ui="$(tmpfile)"
ui_code="$(curl_json POST "$UI_BASE/api/pipeline/guidelines" "$guidelines_payload" "$guidelines_ui")"
[[ "$ui_code" == "200" ]] \
  || fail "POST $UI_BASE/api/pipeline/guidelines HTTP $ui_code — $(head -c 300 "$guidelines_ui")"
jq -e '.prohibited_tickers | length >= 0' "$guidelines_ui" >/dev/null \
  || fail "UI guidelines missing prohibited_tickers"
prohibited_ui="$(jq -c '.prohibited_tickers' "$guidelines_ui")"
[[ "$prohibited_ui" == "$prohibited_direct" ]] \
  || fail "UI vs direct prohibited_tickers mismatch: ui=$prohibited_ui direct=$prohibited_direct"

# --- Granular pipeline steps 2–3 (same sequence as usePipeline.ts) ---
step "POST $UI_BASE/api/pipeline/portfolio (granular step 2)"
portfolio_tmp="$(tmpfile)"
portfolio_payload="$(jq -n \
  --argjson pv "$PORTFOLIO_VALUE" \
  --argjson qty "$QTY_SYMBOLS" \
  --argjson banned "$prohibited_ui" \
  '{portfolio_value: $pv, qty_symbols: $qty, prohibited_tickers: $banned}')"
portfolio_code="$(curl_json POST "$UI_BASE/api/pipeline/portfolio" "$portfolio_payload" "$portfolio_tmp")"
[[ "$portfolio_code" == "200" ]] \
  || fail "POST $UI_BASE/api/pipeline/portfolio HTTP $portfolio_code — $(head -c 300 "$portfolio_tmp")"
portfolio_len="$(jq '.portfolio | length' "$portfolio_tmp")"
[[ "$portfolio_len" == "$QTY_SYMBOLS" ]] \
  || fail "expected $QTY_SYMBOLS positions, got $portfolio_len"

step "POST $UI_BASE/api/pipeline/var (granular step 3)"
var_tmp="$(tmpfile)"
var_payload="$(jq -n --argjson pf "$(jq '.portfolio' "$portfolio_tmp")" '{portfolio: $pf}')"
var_code="$(curl_json POST "$UI_BASE/api/pipeline/var" "$var_payload" "$var_tmp")"
[[ "$var_code" == "200" ]] \
  || fail "POST $UI_BASE/api/pipeline/var HTTP $var_code — $(head -c 300 "$var_tmp")"
value_at_risk="$(jq '.valueAtRisk' "$var_tmp")"
awk -v v="$value_at_risk" 'BEGIN { exit !(v > 0) }' \
  || fail "valueAtRisk=$value_at_risk (expected > 0)"

# --- UI image: VITE LLM vars baked at build (fixes empty Connection settings) ---
step "UI build — VITE_OPENAI_* baked into assets"
if [[ -z "${OPENAI_API_ENDPOINT:-}" ]]; then
  echo "  (skip: OPENAI_API_ENDPOINT not set in $ENV_FILE)"
else
  llm_host="$(echo "$OPENAI_API_ENDPOINT" | sed -E 's#^https?://##' | cut -d/ -f1)"
  if podman compose -f deploy/local/compose.yml exec ui sh -c \
    "grep -q '${llm_host}' /usr/share/nginx/html/assets/*.js" 2>/dev/null; then
    echo "  found LLM host in built JS: $llm_host"
  else
    fail "LLM URL host '$llm_host' not found in UI assets — rebuild with: podman compose --env-file .env -f deploy/local/compose.yml up -d --build ui"
  fi
fi

echo ""
echo "PASS: UI /api proxy verification"
echo "  static page:              HTTP 200"
echo "  /api/health:            ok"
echo "  guidelines (direct):    HTTP 200 — prohibited $prohibited_direct"
echo "  guidelines (via nginx): HTTP 200 — matches direct"
echo "  portfolio (via nginx):  HTTP 200 — $portfolio_len position(s)"
echo "  var (via nginx):        HTTP 200 — valueAtRisk \$$value_at_risk"
exit 0
