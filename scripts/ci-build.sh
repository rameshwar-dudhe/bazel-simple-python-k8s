#!/usr/bin/env bash
# Build + test everything CI cares about, in one place.
#
# The point of putting this in a script instead of inlining it in
# .circleci/config.yml: a developer can reproduce the exact CI command locally,
# and switching CI systems (Jenkins/GitLab) does not mean rewriting the logic.
#
# Usage: scripts/ci-build.sh [extra bazel flags...]
set -euo pipefail

cd "$(dirname "$0")/.."

BAZEL="${BAZEL:-bazel}"
# --config=ci is defined in .bazelrc; CI adds --config=remotecache / --config=rbe.
CONFIGS="${BAZEL_CONFIGS:---config=ci}"

echo "==> bazel version"
"$BAZEL" --version

echo "==> build everything"
# shellcheck disable=SC2086
"$BAZEL" build $CONFIGS //... "$@"

echo "==> test everything (hermetic tests only; smoke tests are tagged manual)"
# shellcheck disable=SC2086
"$BAZEL" test $CONFIGS //... "$@"

echo "==> lock file is in sync with requirements.in"
# shellcheck disable=SC2086
"$BAZEL" test $CONFIGS //third_party/python:requirements.test "$@"

echo "==> build graph sanity: no target may depend on a //tools/... test helper"
if "$BAZEL" query 'rdeps(//services/..., //tools/...)' 2>/dev/null | grep -q .; then
  echo "ERROR: a service depends on //tools/... - tooling must not ship in an image" >&2
  exit 1
fi

echo "OK"
