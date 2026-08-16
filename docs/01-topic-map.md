# 01 — Topic map: every JD line → where it lives → what to say

This is the index for the whole repo. Each row is a JD bullet, the file that
implements it, and the one sentence to say when the interviewer gets there.

## Key Responsibilities

### 1. "Keep CI/CD pipelines (CircleCI) stable, fast and scalable — workflow optimization, configuration management, reusable orbs/commands"

| where | what |
|---|---|
| `.circleci/config.yml` → `commands:` | 6 reusable commands (`setup_bazel`, `restore_bazel_cache`, `save_bazel_cache`, `auth_gar`, `install_crane`, `notify_failure`) — the in-repo equivalent of an orb |
| `.circleci/config.yml` → `orbs:` | `circleci/gcp-cli`, `circleci/slack` — versioned, so an upgrade is a one-line diff |
| `.circleci/config.yml` → `executors:` | one place to bump the toolchain image for every job |
| `.circleci/config.yml` → `workflows:` | 5 workflows (`pr`, `main`, `nightly`, `release`, `hotfix`) out of one config, selected by `when:` + pipeline parameters |
| `scripts/*.sh` | every job body is a script, so CI has *wiring*, not logic |

**Say this:** "Stability and speed come from three things: nothing in the
pipeline is copy-pasted (reusable commands + parameterised jobs), the expensive
work is cached (Bazel remote cache, read-write on main, read-only on PRs so a
PR can't poison it), and every job body is a script in `scripts/` that I can
reproduce locally — which is also what makes it portable if we ever move off
CircleCI."

### 2. "Maintain the Bazel ecosystem (Go, Rust, Python), including RBE setup, caching, troubleshooting and build-graph health"

| where | what |
|---|---|
| `MODULE.bazel` | bzlmod, hermetic CPython 3.11, pip lock, OCI base pinned by digest |
| `MODULE.bazel.lock` | committed → CI resolves the exact same graph as a laptop |
| `.bazelrc` → `--config=rbe` | remote executor + BES + `--jobs=100` + an explicit `--platforms` |
| `platforms/BUILD.bazel` | the RBE execution platform, incl. the worker container image |
| `.bazelrc` → `--config=remotecache` / `remotecache_ro` | shared HTTP cache with `--remote_local_fallback` |
| `.bazelrc` → `--incompatible_strict_action_env` | the classic "why is nothing cached in CI" fix |
| `libs/version/BUILD.bazel` | codegen in the graph: `version.txt → version.py → libs → services → images` |
| `tools/bazel/py_image.bzl` | a reusable macro instead of copy-pasted rules per service |
| `scripts/ci-build.sh` | a `bazel query` graph-health guard: no service may depend on `//tools/...` |

**Say this:** "This repo is Python-only for size, but the mechanics are
language-agnostic: adding Go is `bazel_dep(rules_go)` + `go_binary` targets, and
the same `py_image`-style macro pattern gives you `go_image`. What matters is
that the graph, the caching and the release tooling don't change per language."

### 3. "Maintain and improve our CircleCI setup, workflow optimization and configuration management"

See row 1, plus:
- `parameters:` at pipeline level → the nightly/hotfix pipelines are the *same*
  config triggered with different parameters (no duplicated config files).
- `filters` + a YAML anchor (`&release_filters`) so tag filters are declared once.
- `hold_for_production` approval job — production is never automatic.

### 4. "CI release pipeline (nightly and release modes), multi-image releases driven by manifest/version files"

| where | what |
|---|---|
| `release/manifest.yaml` | the list of images, their repos, versions, and whether they get smoke-tested |
| `release/version.txt` | one version for the monorepo; feeds both the build and the release |
| `tools/release/release.py` | modes `nightly` / `release` / `hotfix`, `--only`, `--registry`, `--dry-run`, JSON report |
| `tools/release/release_test.py` | the tag rules are unit tested — no registry needed |
| `.circleci/config.yml` → `publish` job | one job, `mode` is a parameter |

**Say this:** "CI knows nothing about which services exist. Adding a service to
the release is a manifest PR, not a CI PR. Every mode publishes at least one
*immutable* tag (`1.4.0`, `nightly-20260816-abc1234`) and floating tags
(`latest`, `nightly`) are only ever additional — so a rollback is always 'pin
the immutable tag'."

### 5. "Build and publish artifacts (container images, Helm charts) to GAR / JFrog using tools like crane; manage hotfix delivery to customers"

| where | what |
|---|---|
| `tools/bazel/py_image.bzl` | `oci_image` + `oci_load` + `oci_push`, reproducible layers (`portable_mtime`) |
| `tools/release/release.py` → `publish()` | `crane push` + `crane tag` + `crane digest`; falls back to `docker` |
| `scripts/release.sh` | `helm package` + `helm push` (OCI chart) alongside the images |
| `.circleci/config.yml` → `auth_gar` | GAR auth via Workload Identity Federation (OIDC), no JSON key |
| `--registry` flag + `hotfix` mode | ship one component into a customer's own registry, without touching `latest` |

**Say this:** "crane matters because it talks to the registry directly — no
docker daemon in CI, and re-tagging is a metadata call instead of re-uploading
layers. `crane digest` gives me the immutable reference I record in the release
report and deploy by."

### 6. "Develop, maintain and run build + smoke validation in the pipeline"

| where | what |
|---|---|
| `bazel test //...` | hermetic unit tests, run in the `build_and_test` job |
| `tests/smoke/smoke_test.py` | post-deploy validation: health, **deployed version == released version**, business endpoint |
| `tests/smoke/BUILD.bazel` | `tags = ["manual", "external"]` so it never runs (or caches) in the hermetic suite |
| `.circleci/config.yml` → `deploy_and_smoke` | smoke runs after `helm upgrade`, and a failure triggers `helm rollback` |
| `build_and_test` job | JUnit XML → `store_test_results` for flaky-test insights |

**Say this:** "The assertion that actually earns its keep is comparing
`/version` with the tag the pipeline just published — a rollout can report
success while the cluster still serves the old image."

### 7. "Partner with engineering teams to roll out infrastructure changes and best practices"

| where | what |
|---|---|
| `tools/bazel/py_image.bzl` | platform team owns one macro; changing the base image for all services is a one-line diff |
| `deploy/helm/pyapp` | one chart, teams override values, they don't write manifests |
| `scripts/lint.sh` | the guard rails run the same way locally and in CI |
| `docs/` | the rollout is documented, not tribal knowledge |

## Required Qualifications

| JD line | where |
|---|---|
| Bazel in a multi-language monorepo | `MODULE.bazel`, `libs/`, `services/`, `tools/bazel/py_image.bzl` (see the note in row 2 about adding Go/Rust) |
| CI/CD, pipeline-as-code, workflow optimization | `.circleci/config.yml`, `scripts/ci-build.sh` |
| GAR and/or JFrog | `release/manifest.yaml` (registry prefix), `auth_gar` command, `--registry` override |
| Strong Python and Bash | `tools/release/release.py` (+ tests), `scripts/*.sh` (`set -euo pipefail` everywhere) |
| Linux/CLI | everything is a CLI; `scripts/` is pure POSIX-ish bash |
| Dependency management at scale | `third_party/python/requirements.in` → hashed lock, one version of a library repo-wide, `requirements.test` fails CI if the lock drifts |
| Ownership / problem solving | the `--dry-run` mode, the release report, the rollback-on-smoke-failure step |

## Preferred Qualifications

| JD line | where |
|---|---|
| Docker | Bazel-built OCI images, `oci_load` into the daemon, `setup_remote_docker` in CI |
| Other CI tools | `scripts/*.sh` are CI-agnostic; porting to GitLab/Jenkins = rewriting only the wiring (see `docs/03-circleci.md`) |
| Python package management | `third_party/python/` (pip-compile lock, hashes, `requirement()` in BUILD files) |
| GCP (GAR, gcloud) | `auth_gar`, `gcp-cli` orb with OIDC, GAR-style registry prefixes |
| Best practices / coding standards | unit tests for the release logic, `scripts/lint.sh`, comments that explain *why* |
