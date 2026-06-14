#!/usr/bin/env bash
#
# Bootstrap a single-node MicroShift (OKD) cluster inside a Podman container,
# then install KServe and NemoGuardrails CRDs so that OpenShift AI custom
# resources are accepted by the API server for Helm-based e2e testing.
#
# NOTE: Only CRDs are installed — no controllers. CRs will be created and
# stored but not reconciled (no status updates, no pods spawned by KServe).
# This is intentional for CI: we validate that the Helm chart deploys cleanly
# and that application-level services (orchestrator, UI, tool agents) work.
#
# Usage:
#   ci/setup-microshift.sh              # uses defaults
#   KUBECONFIG=/tmp/kc ci/setup-microshift.sh
#
# Outputs:
#   - KUBECONFIG file (default: /tmp/microshift-kubeconfig)
#   - Running MicroShift container named "microshift-okd-1"
#
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
MICROSHIFT_REPO="${MICROSHIFT_REPO:-https://github.com/microshift-io/microshift.git}"
MICROSHIFT_DIR="${MICROSHIFT_DIR:-/tmp/microshift-upstream}"
KUBECONFIG="${KUBECONFIG:-/tmp/microshift-kubeconfig}"
KSERVE_VERSION="${KSERVE_VERSION:-v0.16.0}"
NEMO_CONTROLLER_REPO="https://raw.githubusercontent.com/trustyai-explainability/nemo-guardrails-controller/main"

export KUBECONFIG

log() { echo ">>> $*"; }

# ── 1. Clone upstream MicroShift ─────────────────────────────────────
log "Cloning microshift-io/microshift..."
if [ -d "$MICROSHIFT_DIR" ]; then
	log "Directory $MICROSHIFT_DIR already exists, reusing."
else
	git clone --depth=1 "$MICROSHIFT_REPO" "$MICROSHIFT_DIR"
fi

# ── 2. Pull the latest bootc image (or load from cache) ─────────────
if [ -n "${MICROSHIFT_TAG:-}" ]; then
	TAG="$MICROSHIFT_TAG"
	log "Using pre-resolved MicroShift tag: $TAG"
else
	log "Fetching latest MicroShift release tag..."
	TAG=$(curl -sf --max-time 30 \
		"https://api.github.com/repos/microshift-io/microshift/releases/latest" |
		jq -r .tag_name)
	if [ -z "$TAG" ] || [ "$TAG" = "null" ]; then
		echo "ERROR: Could not determine latest MicroShift release tag"
		exit 1
	fi
fi

IMAGE="ghcr.io/microshift-io/microshift:${TAG}"
CACHE_TAR="${MICROSHIFT_IMAGE_CACHE:-}"

if sudo podman image exists "$IMAGE" 2>/dev/null; then
	log "Image $IMAGE already present locally, skipping pull."
elif [ -n "$CACHE_TAR" ] && [ -f "$CACHE_TAR" ]; then
	log "Loading $IMAGE from cache ($CACHE_TAR) ..."
	sudo podman load -i "$CACHE_TAR"
else
	log "Pulling $IMAGE ..."
	sudo podman pull "$IMAGE"
	if [ -n "$CACHE_TAR" ]; then
		log "Saving image to cache ($CACHE_TAR) ..."
		mkdir -p "$(dirname "$CACHE_TAR")"
		sudo podman save -o "$CACHE_TAR" "$IMAGE"
		sudo chown "$(id -u):$(id -g)" "$CACHE_TAR"
	fi
fi

sudo podman tag "$IMAGE" localhost/microshift-okd:latest

# ── 3. Start MicroShift ──────────────────────────────────────────────
log "Starting MicroShift cluster..."
make -C "$MICROSHIFT_DIR" run

log "Waiting for cluster readiness..."
make -C "$MICROSHIFT_DIR" run-ready

log "Waiting for cluster health..."
make -C "$MICROSHIFT_DIR" run-healthy

# ── 4. Extract kubeconfig ────────────────────────────────────────────
log "Extracting kubeconfig to $KUBECONFIG ..."
sudo podman cp microshift-okd-1:/var/lib/microshift/resources/kubeadmin/kubeconfig "$KUBECONFIG"
sudo chown "$(id -u):$(id -g)" "$KUBECONFIG"

MICROSHIFT_IP=$(sudo podman inspect microshift-okd-1 |
	jq -r '.[0].NetworkSettings.Networks | to_entries[0].value.IPAddress')

if [ -z "$MICROSHIFT_IP" ] || [ "$MICROSHIFT_IP" = "null" ]; then
	echo "ERROR: Could not determine MicroShift container IP"
	exit 1
fi

sed -i "s|server: https://.*:6443|server: https://${MICROSHIFT_IP}:6443|" "$KUBECONFIG"

# The server cert is issued for localhost/internal names, not the container IP.
# Disable TLS verification so oc/kubectl work from the host.
CLUSTER_NAME=$(oc config get-clusters 2>/dev/null | tail -1)
if [ -n "$CLUSTER_NAME" ]; then
	oc config set-cluster "$CLUSTER_NAME" --insecure-skip-tls-verify=true
fi

log "API server at https://${MICROSHIFT_IP}:6443"

oc get nodes
echo ""

# ── 5. Install KServe CRDs (no controller) ──────────────────────────
log "Installing KServe CRDs ${KSERVE_VERSION} (CRDs only, no controller)..."

helm install kserve-crd oci://ghcr.io/kserve/charts/kserve-crd \
	--version "$KSERVE_VERSION" \
	--namespace kserve --create-namespace \
	--wait --timeout 120s

log "KServe CRDs installed. Verifying..."
oc get crd inferenceservices.serving.kserve.io
oc get crd servingruntimes.serving.kserve.io

# ── 6. Install NemoGuardrails CRD (no controller) ───────────────────
log "Installing NemoGuardrails CRD..."
oc apply -f "${NEMO_CONTROLLER_REPO}/config/crd/bases/trustyai.opendatahub.io_nemoguardrails.yaml"

log "Verifying NemoGuardrails CRD..."
oc get crd nemoguardrails.trustyai.opendatahub.io

# ── 7. Final verification ───────────────────────────────────────────
echo ""
log "=== MicroShift + OpenShift AI CRDs setup complete ==="
echo ""
echo "  KUBECONFIG=$KUBECONFIG"
echo "  MicroShift IP=$MICROSHIFT_IP"
echo ""
echo "  CRDs installed:"
oc get crds | grep -E "inferenceservice|servingruntime|nemoguardrails" || true
echo ""
oc get nodes
echo ""
oc get pods -A --no-headers | head -20
