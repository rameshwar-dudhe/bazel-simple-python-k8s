#!/usr/bin/env bash
# Remove everything this repo deployed, so the next run is a true from-scratch
# deploy. Safe to run twice - every step tolerates "already gone".
#
# It only ever touches things this repo created:
#   * the Helm release + its namespace
#   * local docker images tagged <registry>/pyplatform/*
#   * the pyplatform/* repositories in the demo registry
#   * local build outputs (bazel-out, dist/, release-report.json)
#
# Usage:
#   scripts/teardown.sh                 # cluster + images + build outputs
#   KEEP_BAZEL_CACHE=1 scripts/teardown.sh   # skip `bazel clean` (faster redeploy)
set -euo pipefail

cd "$(dirname "$0")/.."

NAMESPACE="${NAMESPACE:-pyplatform}"
RELEASE="${RELEASE_NAME:-pyplatform}"
HOST_IP="$(hostname -I | awk '{print $1}')"
REGISTRY_HOST="${REGISTRY_HOST:-${HOST_IP}:5000}"

step() { echo; echo "==> $*"; }

step "1/5 helm release"
if helm -n "$NAMESPACE" status "$RELEASE" >/dev/null 2>&1; then
  helm -n "$NAMESPACE" uninstall "$RELEASE" --wait
else
  echo "    no release '$RELEASE' in ns/$NAMESPACE - nothing to do"
fi

step "2/5 namespace"
if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  kubectl delete ns "$NAMESPACE" --wait --timeout=120s
else
  echo "    no namespace '$NAMESPACE' - nothing to do"
fi

step "3/5 local docker images"
mapfile -t IMAGES < <(docker images --format '{{.Repository}}:{{.Tag}}' \
  | grep -E '/pyplatform/(api|worker):' || true)
if [[ ${#IMAGES[@]} -gt 0 ]]; then
  docker rmi -f "${IMAGES[@]}" >/dev/null
  printf '    removed %s\n' "${IMAGES[@]}"
else
  echo "    no pyplatform images in the local docker daemon"
fi

step "4/5 registry repositories (${REGISTRY_HOST})"
# A registry:2 container only honours DELETE when it was started with
# REGISTRY_STORAGE_DELETE_ENABLED=true. If it refuses, the tags simply get
# overwritten by the next push - the demo still starts clean.
for repo in pyplatform/api pyplatform/worker; do
  tags="$(curl -fsS "http://${REGISTRY_HOST}/v2/${repo}/tags/list" 2>/dev/null \
    | python3 -c 'import json,sys; print(" ".join(json.load(sys.stdin).get("tags") or []))' 2>/dev/null || true)"
  if [[ -z "$tags" ]]; then
    echo "    ${repo}: nothing published"
    continue
  fi
  for tag in $tags; do
    digest="$(curl -fsSI \
      -H 'Accept: application/vnd.oci.image.index.v1+json' \
      -H 'Accept: application/vnd.oci.image.manifest.v1+json' \
      -H 'Accept: application/vnd.docker.distribution.manifest.v2+json' \
      -H 'Accept: application/vnd.docker.distribution.manifest.list.v2+json' \
      "http://${REGISTRY_HOST}/v2/${repo}/manifests/${tag}" 2>/dev/null \
      | tr -d '\r' | awk -F': ' '/[Dd]ocker-[Cc]ontent-[Dd]igest/ {print $2}')"
    [[ -z "$digest" ]] && continue
    if curl -fsS -X DELETE "http://${REGISTRY_HOST}/v2/${repo}/manifests/${digest}" >/dev/null 2>&1; then
      echo "    ${repo}:${tag} deleted"
    else
      echo "    ${repo}:${tag} - registry refused DELETE (deletion disabled); will be overwritten on next push"
      break
    fi
  done
done

step "5/5 local build outputs"
rm -rf dist/ release-report.json
if [[ -z "${KEEP_BAZEL_CACHE:-}" ]]; then
  bazel clean
else
  echo "    KEEP_BAZEL_CACHE=1 - keeping bazel outputs"
fi

echo
echo "OK - teardown complete. Rebuild with: docs/08-deploy-from-scratch.md"
