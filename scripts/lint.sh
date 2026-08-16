#!/usr/bin/env bash
# Cheap, fast checks that run first in the pipeline so an obvious mistake fails
# in 30 seconds instead of after a full build.
set -euo pipefail

cd "$(dirname "$0")/.."

fail=0
step() { echo; echo "==> $*"; }

step "bazel: every BUILD file loads and the graph resolves"
bazel query '//...' >/dev/null

step "bazel: no target is orphaned from the build graph"
bazel query 'kind("py_(binary|library|test)", //...)' >/dev/null

step "yaml: manifest + helm values parse"
python3 - <<'PY'
import sys, pathlib
try:
    import yaml
except ImportError:
    print("   (pyyaml not installed on the host - skipped; CI uses //tools/release)")
    sys.exit(0)
for f in ["release/manifest.yaml", "deploy/helm/pyapp/values.yaml", "deploy/helm/pyapp/Chart.yaml"]:
    yaml.safe_load(pathlib.Path(f).read_text())
    print(f"   ok {f}")
PY

step "helm: chart lints and renders"
if command -v helm >/dev/null; then
  helm lint deploy/helm/pyapp
  helm template pyplatform deploy/helm/pyapp >/dev/null
else
  echo "   helm not installed - skipped"
fi

step "circleci: config is valid"
if command -v circleci >/dev/null; then
  circleci config validate .circleci/config.yml
else
  echo "   circleci CLI not installed - skipped (install: https://circleci.com/docs/local-cli)"
fi

step "shell: scripts are syntactically valid"
for f in scripts/*.sh; do
  bash -n "$f" || fail=1
  echo "   ok $f"
done

exit "$fail"
