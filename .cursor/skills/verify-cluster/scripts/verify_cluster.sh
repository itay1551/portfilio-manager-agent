#!/usr/bin/env bash
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────
NAMESPACE="${NAMESPACE:-investment-advisor-agent-itay}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-120s}"
REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
RELEASE=investment-advisor-agent

DEPLOYMENTS=(
	ui
	orchestrator
	investment-advisor-agent-risk
	investment-advisor-agent-portfolio
	investment-advisor-agent-guidelines
	minio
)

pass=0
fail=0
report() {
	echo "  [$1] $2"
	if [ "$1" = "PASS" ]; then
		pass=$((pass + 1))
	else
		fail=$((fail + 1))
	fi
}

echo "=== Cluster verification: namespace=$NAMESPACE ==="
echo ""

# ── 0. Helm lint ─────────────────────────────────────────────────────
echo "--- Phase 0: Helm lint ---"
if helm lint "$REPO_ROOT/deploy/helm" --quiet; then
	report PASS "helm lint"
else
	report FAIL "helm lint"
	echo "FAIL: chart has lint errors, aborting."
	exit 1
fi

# ── 1. Undeploy ──────────────────────────────────────────────────────
echo ""
echo "--- Phase 1: Undeploy ---"
if [ "${SKIP_UNDEPLOY:-}" = "1" ]; then
	echo "  (skipped)"
else
	if helm uninstall "$RELEASE" -n "$NAMESPACE" 2>/dev/null; then
		echo "  Removed previous release."
		echo "  Waiting 10s for resources to terminate..."
		sleep 10
	else
		echo "  No existing release found, continuing."
	fi
fi

# ── 2. Deploy ────────────────────────────────────────────────────────
echo ""
echo "--- Phase 2: Deploy ---"
make -C "$REPO_ROOT" deploy-cluster NAMESPACE="$NAMESPACE"
report PASS "helm upgrade --install"

# ── 3. Wait for rollouts ─────────────────────────────────────────────
echo ""
echo "--- Phase 3: Pod rollouts ---"
all_rolled=true
for dep in "${DEPLOYMENTS[@]}"; do
	if oc rollout status "deployment/$dep" -n "$NAMESPACE" --timeout="$ROLLOUT_TIMEOUT" 2>&1; then
		report PASS "rollout $dep"
	else
		report FAIL "rollout $dep"
		all_rolled=false
	fi
done

if [ "$all_rolled" = false ]; then
	echo ""
	echo "FAIL: not all deployments rolled out. Remaining checks skipped."
	echo "  Debug: oc get pods -n $NAMESPACE"
	exit 1
fi

# ── 4. Restart count ─────────────────────────────────────────────────
echo ""
echo "--- Phase 4: Pod restarts ---"
restarts=$(oc get pods -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .status.containerStatuses[*]}{.restartCount}{end}{"\n"}{end}')
has_restarts=false
while IFS= read -r line; do
	[ -z "$line" ] && continue
	pod=$(echo "$line" | awk '{print $1}')
	count=$(echo "$line" | awk '{print $2}')
	if [ "${count:-0}" -gt 0 ]; then
		report FAIL "pod $pod has $count restart(s)"
		has_restarts=true
	fi
done <<<"$restarts"
if [ "$has_restarts" = false ]; then
	report PASS "all pods 0 restarts"
fi

# ── 4b. Model upload Job ─────────────────────────────────────────────
echo ""
echo "--- Phase 4b: Model upload Job ---"
if oc wait --for=condition=Complete job/model-upload -n "$NAMESPACE" --timeout="${ROLLOUT_TIMEOUT}" 2>&1; then
	report PASS "model-upload Job completed"
else
	report FAIL "model-upload Job not completed"
fi

# ── 4c. InferenceService ready ───────────────────────────────────────
echo ""
echo "--- Phase 4c: InferenceService ---"
if oc wait --for=condition=Ready isvc/guidelines-mlp -n "$NAMESPACE" --timeout="${ROLLOUT_TIMEOUT}" 2>&1; then
	report PASS "InferenceService guidelines-mlp Ready"
else
	report FAIL "InferenceService guidelines-mlp not Ready"
	echo "  Debug: oc get isvc guidelines-mlp -n $NAMESPACE -o yaml"
fi

# ── 5. Route health ──────────────────────────────────────────────────
echo ""
echo "--- Phase 5: Route health ---"
UI_HOST=$(oc get route ui -n "$NAMESPACE" -o jsonpath='{.spec.host}')
ORCH_HOST=$(oc get route orchestrator -n "$NAMESPACE" -o jsonpath='{.spec.host}')

if [ -z "$UI_HOST" ] || [ -z "$ORCH_HOST" ]; then
	report FAIL "could not resolve routes (ui=$UI_HOST orchestrator=$ORCH_HOST)"
else
	UI_BASE="http://$UI_HOST"
	ORCH_BASE="http://$ORCH_HOST"

	if curl -sf --max-time 10 "$ORCH_BASE/health" >/dev/null; then
		report PASS "orchestrator /health ($ORCH_BASE)"
	else
		report FAIL "orchestrator /health unreachable ($ORCH_BASE)"
	fi

	if curl -sf --max-time 10 "$UI_BASE/" >/dev/null; then
		report PASS "UI static ($UI_BASE)"
	else
		report FAIL "UI static unreachable ($UI_BASE)"
	fi
fi

# ── 6. UI api proxy ──────────────────────────────────────────────────
echo ""
echo "--- Phase 6: UI api proxy ---"
if [ -n "${UI_BASE:-}" ]; then
	if curl -sf --max-time 15 "$UI_BASE/api/health" >/dev/null; then
		report PASS "UI /api/health proxy"
	else
		report FAIL "UI /api/health proxy"
	fi
else
	report FAIL "UI_BASE not set, skipping proxy check"
fi

# ── 7. Integration tests ─────────────────────────────────────────────
echo ""
echo "--- Phase 7: Integration tests ---"
if [ "${SKIP_TESTS:-}" = "1" ]; then
	echo "  (skipped)"
else
	if make -C "$REPO_ROOT" test-cluster NAMESPACE="$NAMESPACE"; then
		report PASS "integration tests"
	else
		report FAIL "integration tests"
	fi
fi

# ── Summary ───────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  PASS: $pass   FAIL: $fail"
echo "========================================"
[ "$fail" -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit "$fail"
