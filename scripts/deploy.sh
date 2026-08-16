#!/usr/bin/env bash
# Deploy the current release to Kubernetes with Helm, then wait for the rollout.
#
# Usage:
#   scripts/deploy.sh <image-tag> [namespace] [registry-prefix]
#
# Examples:
#   scripts/deploy.sh 1.4.0
#   scripts/deploy.sh nightly-20260816-abc1234 pyplatform-nightly
set -euo pipefail

cd "$(dirname "$0")/.."

TAG="${1:?usage: scripts/deploy.sh <image-tag> [namespace] [registry-prefix]}"
NAMESPACE="${2:-pyplatform}"
# The cluster nodes must be able to resolve the registry, so "localhost:5000"
# only works if the registry runs ON the node. Default to this host's LAN IP.
HOST_IP="$(hostname -I | awk '{print $1}')"
REGISTRY="${3:-${REGISTRY:-${HOST_IP}:5000/pyplatform}}"
RELEASE="${RELEASE_NAME:-pyplatform}"
APP_ENV="${APP_ENV:-dev}"

echo "==> helm lint"
helm lint deploy/helm/pyapp

echo "==> deploying ${REGISTRY}/{api,worker}:${TAG} to ns/${NAMESPACE}"
helm upgrade --install "$RELEASE" deploy/helm/pyapp \
  --namespace "$NAMESPACE" --create-namespace \
  --set image.registry="$REGISTRY" \
  --set image.tag="$TAG" \
  --set env.APP_ENV="$APP_ENV" \
  --wait --timeout 3m

echo "==> rollout status"
kubectl -n "$NAMESPACE" rollout status "deploy/${RELEASE}-pyplatform-api" --timeout=120s

kubectl -n "$NAMESPACE" get deploy,pods,svc,cronjob -l app.kubernetes.io/instance="$RELEASE"
echo "OK"
