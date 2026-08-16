#!/usr/bin/env bash
# One entry point for every kind of release. CI calls exactly this.
#
# Usage:
#   scripts/release.sh nightly
#   scripts/release.sh release
#   scripts/release.sh hotfix api 1        # component + hotfix number
#
# Env:
#   REGISTRY   push destination prefix (default: whatever the manifest says)
#   PUSH       "false" to build + tag only (default true)
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:?usage: scripts/release.sh <nightly|release|hotfix> [component] [hotfix-number]}"
COMPONENT="${2:-}"
HOTFIX_NUMBER="${3:-0}"
PUSH="${PUSH:-true}"

ARGS=(--mode "$MODE" --report release-report.json)
[[ -n "$COMPONENT" ]] && ARGS+=(--only "$COMPONENT")
[[ "$MODE" == "hotfix" ]] && ARGS+=(--hotfix-number "$HOTFIX_NUMBER")
[[ -n "${REGISTRY:-}" ]] && ARGS+=(--registry "$REGISTRY")
[[ "$PUSH" == "true" ]] && ARGS+=(--push)

echo "==> guard: chart appVersion must match release/version.txt"
VERSION="$(tr -d '[:space:]' < release/version.txt)"
CHART_APP_VERSION="$(awk '/^appVersion:/ {gsub(/"/,"",$2); print $2}' deploy/helm/pyapp/Chart.yaml)"
if [[ "$VERSION" != "$CHART_APP_VERSION" ]]; then
  echo "ERROR: version.txt=$VERSION but Chart.yaml appVersion=$CHART_APP_VERSION" >&2
  exit 1
fi

echo "==> running release tool"
bazel run //tools/release -- "${ARGS[@]}"

if [[ "$MODE" == "release" && "$PUSH" == "true" ]]; then
  echo "==> packaging + publishing the Helm chart as an OCI artifact"
  CHART_REGISTRY="${CHART_REGISTRY:-${REGISTRY:-localhost:5000/pyplatform}}"
  helm package deploy/helm/pyapp --destination dist/
  CHART_TGZ="$(ls -t dist/pyplatform-*.tgz | head -1)"
  # Same registry as the images: GAR and JFrog both speak OCI for charts.
  helm push "$CHART_TGZ" "oci://${CHART_REGISTRY%/*}/charts"
fi

echo "OK - see release-report.json"
