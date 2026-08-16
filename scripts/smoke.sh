#!/usr/bin/env bash
# Run the post-deploy smoke validation against a deployed API.
#
# Usage:
#   scripts/smoke.sh <expected-version> [namespace]
#
# Resolves the NodePort URL from the cluster itself, so the same script works
# for a local demo cluster and for a CI-provisioned one.
set -euo pipefail

cd "$(dirname "$0")/.."

EXPECTED_VERSION="${1:?usage: scripts/smoke.sh <expected-version> [namespace]}"
NAMESPACE="${2:-pyplatform}"
RELEASE="${RELEASE_NAME:-pyplatform}"

if [[ -z "${SMOKE_BASE_URL:-}" ]]; then
  NODE_IP="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')"
  NODE_PORT="$(kubectl -n "$NAMESPACE" get svc "${RELEASE}-pyplatform-api" -o jsonpath='{.spec.ports[0].nodePort}')"
  SMOKE_BASE_URL="http://${NODE_IP}:${NODE_PORT}"
fi

echo "==> smoke testing ${SMOKE_BASE_URL} (expecting version ${EXPECTED_VERSION})"
SMOKE_BASE_URL="$SMOKE_BASE_URL" EXPECTED_VERSION="$EXPECTED_VERSION" \
  bazel test //tests/smoke:smoke_test \
    --test_env=SMOKE_BASE_URL --test_env=EXPECTED_VERSION \
    --test_output=all --nocache_test_results
