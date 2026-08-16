# pyplatform — a small Bazel/CircleCI/Kubernetes monorepo for DevOps interview prep

A deliberately small Python monorepo that contains **one real example of every
responsibility in the job description**: Bazel multi-language-style monorepo,
CircleCI pipeline-as-code with nightly/release/hotfix modes, manifest-driven
multi-image releases pushed with `crane` to GAR/JFrog-style registries, Helm
charts, smoke validation, and Python/Bash tooling.

Two services, one shared library, ~600 lines of Python. Small enough to hold in
your head in an interview, complete enough that every JD bullet has something
you can point at.

> **Where to start:** [`docs/01-topic-map.md`](docs/01-topic-map.md) maps every
> line of the JD to the file that implements it, and to what to say about it.

---

## What is in here

```
MODULE.bazel              bzlmod: hermetic python 3.11, pip lock, OCI base image
.bazelrc                  build configs: ci / remotecache / rbe
.circleci/config.yml      5 workflows: pr, main, nightly, release, hotfix
libs/greeter/             shared library - the shared node in the build graph
libs/version/             genrule codegen: release/version.txt -> version.py
services/api/             HTTP service (stdlib) + unit tests + OCI image
services/worker/          batch CLI + unit tests + OCI image (2nd image!)
third_party/python/       requirements.in -> fully hashed requirements_lock.txt
tools/bazel/py_image.bzl  reusable macro: py_binary -> OCI image/tarball/push
tools/release/release.py  manifest-driven release tool (nightly/release/hotfix)
release/manifest.yaml     THE source of truth for what gets released
release/version.txt       THE source of truth for the version
deploy/helm/pyapp/        Helm chart: api Deployment + worker CronJob
tests/smoke/              post-deploy smoke validation (manual bazel target)
scripts/                  bash entry points that CI and humans both call
docs/                     the interview prep material
```

## Quickstart

```bash
bazel test //...                      # 4 hermetic tests, no docker/cluster needed
bazel run //services/api              # http://localhost:8080/greet?name=you
make image                            # build both OCI images with Bazel
bazel run //tools/release -- --mode nightly --dry-run   # what would ship?
```

Full end-to-end (needs docker + a registry + a cluster) — the whole
teardown-to-smoke procedure is written up in
[`docs/08-deploy-from-scratch.md`](docs/08-deploy-from-scratch.md):

```bash
scripts/teardown.sh                   # wipe any previous deploy (idempotent)
scripts/release.sh release            # build, tag 1.4.0/1.4/latest, push
scripts/deploy.sh 1.4.0               # helm upgrade --install + rollout wait
scripts/smoke.sh 1.4.0                # smoke test the deployed version
```

## This was actually run, not just written

On the machine this repo was built on, the whole chain executed for real:

| step | result |
|---|---|
| `bazel test //...` | 4/4 pass (hermetic, no network) |
| `bazel run //services/api:image_tarball` | image loaded into docker, container serves `/version` |
| `scripts/release.sh release` (crane push) | `pyplatform/api:{1.4.0,1.4,latest}` + `pyplatform/worker:...` in the registry |
| `scripts/deploy.sh 1.4.0` | 2/2 API pods Ready + worker CronJob created on a real k8s 1.36 cluster |
| `scripts/smoke.sh 1.4.0` | 3/3 smoke assertions pass against the NodePort |
| `circleci config validate` | `.circleci/config.yml is valid` |

## Docs

| doc | what it covers |
|---|---|
| [01-topic-map.md](docs/01-topic-map.md) | **JD line → file → talking point** (read this first) |
| [02-bazel.md](docs/02-bazel.md) | bzlmod, build graph, caching, RBE, dependency management, troubleshooting |
| [03-circleci.md](docs/03-circleci.md) | workflows, reusable commands/orbs, nightly/release triggers, optimization |
| [04-release-registries.md](docs/04-release-registries.md) | manifest-driven multi-image release, tag strategy, crane, GAR/JFrog, hotfixes |
| [05-k8s-helm-smoke.md](docs/05-k8s-helm-smoke.md) | Helm chart, rollout, smoke validation, rollback |
| [06-interview-qa.md](docs/06-interview-qa.md) | likely questions with answers grounded in this repo |
| [07-runbook.md](docs/07-runbook.md) | every command, with the output you should expect |
| [08-deploy-from-scratch.md](docs/08-deploy-from-scratch.md) | **teardown → rebuild → release → deploy → smoke**, verified end to end |
