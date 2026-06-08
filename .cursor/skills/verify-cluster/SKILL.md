---
name: verify-cluster
description: Cluster deployment verification on OpenShift. Redeploys via Helm, waits for pods, checks routes, runs integration tests, then verifies the UI in Chrome via chrome-devtools MCP. Use when the user says "verify cluster", "redeploy cluster", or "test on cluster" — not for local Podman Compose.
---

# Verify Cluster Deployment (OpenShift)

Full teardown-redeploy-verify cycle on OpenShift. Requires `oc` login.

## Flow

1. **Script first** — `verify_cluster.sh` (Helm, pods, routes, pytest).
2. **Browser MCP second** — chrome-devtools MCP on the cluster UI route ([browser-mcp.md](../browser-mcp.md)).
3. Skip browser with `SKIP_BROWSER_MCP=1`.

**Project namespace:** `investment-advisor-agent-itay` (always use this unless the user specifies another).

## Usage

```bash
.cursor/skills/verify-cluster/scripts/verify_cluster.sh
```

Or step-by-step when you need control over individual phases:

```bash
NAMESPACE=investment-advisor-agent-itay

# 1. Undeploy
helm uninstall investment-advisor-agent -n $NAMESPACE

# 2. Redeploy
make deploy-cluster NAMESPACE=$NAMESPACE

# 3. Wait + verify
.cursor/skills/verify-cluster/scripts/verify_cluster.sh
```

## What the script does

| Phase | Check | How |
|-------|-------|-----|
| 0 | Helm lint | `helm lint deploy/helm` |
| 1 | Undeploy | `helm uninstall` (tolerates "not found") |
| 2 | Deploy | `make deploy-cluster NAMESPACE=...` |
| 3 | Pods ready | `oc rollout status` on all 5 deployments |
| 4 | No restarts | Pod restart count == 0 |
| 5 | Route health | `GET /health` on orchestrator route, `GET /` on UI route |
| 6 | UI api proxy | `GET <ui-route>/api/health` — nginx proxies to orchestrator |
| 7 | Integration tests | `make test-cluster NAMESPACE=...` |
| 8 | Browser UI (MCP) | chrome-devtools — pipeline + chat on UI route ([browser-mcp.md](../browser-mcp.md)) |

After script exit `0`, resolve UI URL and run browser MCP (unless `SKIP_BROWSER_MCP=1`):

```bash
NAMESPACE="${NAMESPACE:-investment-advisor-agent-itay}"
UI_BASE="http://$(oc get route ui -n "$NAMESPACE" -o jsonpath='{.spec.host}')"
```

Then follow [browser-mcp.md](../browser-mcp.md) using `$UI_BASE`. Requires **chrome-devtools** MCP (`.cursor/mcp.json`, gitignored).

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NAMESPACE` | `investment-advisor-agent-itay` | OpenShift project/namespace |
| `ROLLOUT_TIMEOUT` | `120s` | Max wait per deployment rollout |
| `SKIP_UNDEPLOY` | off | Set to `1` to skip `helm uninstall` |
| `SKIP_TESTS` | off | Set to `1` to skip pytest |
| `SKIP_BROWSER_MCP` | off | Set to `1` to skip chrome-devtools UI verification |

## On failure

1. Read the `FAIL:` line from script output.
2. Check pod logs: `oc logs deploy/<name> -n $NAMESPACE`
3. Check events: `oc get events -n $NAMESPACE --sort-by=.lastTimestamp | tail -20`
4. For image pull issues: verify `oc get deployment <name> -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].image}'`

## Report (after PASS)

```markdown
## Cluster verification

**Status:** PASS / FAIL
**Namespace:** investment-advisor-agent-itay
**Method:** verify_cluster.sh
**Pods:** all 5 Running, 0 restarts
**Routes:** orchestrator + UI healthy
**UI proxy:** /api/health OK
**Integration tests:** X passed, Y skipped
**Browser MCP:** PASS — pipeline complete on $UI_BASE; chat swap ok; console clean
**Blockers:** none
```
