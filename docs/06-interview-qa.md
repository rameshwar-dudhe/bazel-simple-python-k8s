# 06 — Likely questions, answered from this repo

Answer pattern that works: **short answer → the mechanism → point at the file →
the trade-off you knowingly took.**

## Bazel

**Q: Why Bazel instead of make/tox/docker build?**
Correct incremental builds across languages. Bazel knows the exact inputs of
every action, so it rebuilds and retests only what a change affects, and the
same graph gives you a shared cache and remote execution for free. In this repo
`bazel query 'rdeps(//..., //libs/greeter)'` shows the blast radius of a change
before I make it.

**Q: WORKSPACE vs bzlmod?**
bzlmod (`MODULE.bazel`) resolves external deps from a registry with real version
resolution, instead of a script where order matters and every repo re-invents
its pins. `MODULE.bazel.lock` is committed so CI resolves the identical graph.
Migration is usually incremental — both can coexist during the move.

**Q: Our CI cache never hits. Where do you look?**
In order: (1) is the action environment leaking? `--incompatible_strict_action_env`;
(2) are the toolchains hermetic, or is a system python/compiler sneaking in?
(3) are outputs reproducible — timestamps in tars/images are the usual culprit
(`portable_mtime = True` here); (4) compare two invocations with
`--execution_log_compact_file` and diff the action keys; (5) check the PR jobs
aren't uploading garbage (we make PRs read-only on purpose).

**Q: How do you set up RBE?**
Point `--remote_executor` at the cluster, declare an execution platform with the
worker image in `exec_properties` (`platforms/BUILD.bazel`), make every toolchain
hermetic, raise `--jobs` because the bottleneck is now the network, and use
`--remote_download_toplevel` so you don't drag every intermediate output back.
Then watch the BES invocation URL for actions falling back to local execution —
that is always an undeclared dependency.

**Q: A build works locally and fails on RBE. First move?**
`bazel aquery` the failing action and look at its declared inputs. 90% of the
time something is used but not declared, and the local sandbox was lenient.

**Q: How would you add Go or Rust here?**
`bazel_dep(name = "rules_go", ...)` / `rules_rust`, plus a `go_image` macro next
to `py_image.bzl`. Nothing about the release manifest, the CI config or the Helm
chart changes — that separation is the point of the design.

**Q: How do you keep the build graph healthy?**
Enforced boundaries (`visibility`), a CI query guard — `scripts/ci-build.sh`
fails if a service ever depends on `//tools/...` — no cyclic or "god" targets,
and watching for targets whose dependency count grows faster than their code.

## CI/CD

**Q: How do you make a slow pipeline fast?**
Measure first (CircleCI insights + the BES invocation), then: fail cheap checks
first, cache the expensive layer (Bazel remote cache), stop redoing work across
jobs (`persist_to_workspace`), and only then add parallelism. In this repo I
deliberately did *not* shard tests, because Bazel already skips unchanged ones —
sharding would add container startup cost for little gain.

**Q: Nightly vs release — how do you avoid two copies of the pipeline?**
Pipeline parameters. `run_nightly=true` from a scheduled pipeline selects the
`nightly` workflow, and it reuses the same `build_and_test`/`publish`/
`deploy_and_smoke` jobs with different parameters. The only thing that differs
is the release *mode*, which is a flag to `tools/release`.

**Q: How do you handle secrets?**
Contexts scoped to branches/teams, OIDC (Workload Identity Federation) for GAR
so there is no long-lived JSON key, short-lived tokens fed to `crane auth login`,
and nothing secret in the config or in `scripts/`.

**Q: A PR from a fork — what can it do?**
Build and test, read the cache, and nothing else. No publish job runs, the
cache is read-only, and no context is attached to the `pr` workflow.

**Q: Config is getting long. What now?**
Extract the reusable commands into a private org orb, keep job bodies as scripts
in the repo, and use `setup` workflows with dynamic config generation if
different parts of the monorepo need genuinely different pipelines.

## Releases and registries

**Q: Walk me through a release.**
Tag `v1.4.0` → `release` workflow → build/test with the shared cache → the
release tool reads `release/manifest.yaml`, builds each image with Bazel, tags
`1.4.0`/`1.4`/`latest`, pushes with crane, records digests in
`release-report.json` → chart packaged and pushed as an OCI artifact → deploy to
staging with the immutable tag → smoke test → manual approval → prod.

**Q: Why a manifest file instead of listing images in the CI config?**
Because then CI has to change every time a team ships a new service. The
manifest is owned by the teams, reviewed like code, and the same file drives
local runs and CI. It is also what makes a partial (hotfix) release trivial:
`--only api`.

**Q: `latest` — yes or no?**
Publish it, never deploy it. It is a convenience pointer for humans; the
deployment always references an immutable tag or a digest, otherwise rollback
is undefined.

**Q: Why crane over docker?**
No daemon, and re-tagging/copying is a registry metadata operation instead of a
layer upload. `crane copy` is how you promote an artifact between registries
(staging→prod, GAR→a customer's JFrog) without ever pulling it.

**Q: A customer needs a fix on 1.4.0 but main is already on 1.6.**
Branch from the release tag, cherry-pick, run the `hotfix` pipeline for just
that component with `--registry <customer registry>`; it publishes
`1.4.0-hotfix.1` and does not touch `latest`. The release report goes on the
ticket so support knows exactly which digest the customer runs.

## Kubernetes / validation

**Q: What do you smoke test after a deploy?**
Health, **the deployed version equals the released version**, and one real
endpoint. The version check is the one that catches the failure mode people
actually hit — a "successful" rollout still serving the old image.

**Q: Smoke test fails at 2am. What happens?**
The job's `on_fail` step runs `helm rollback`, Slack gets a failure notification
with the invocation link, and the release report plus the immutable tag say
exactly what was deployed. Then the fix goes through the normal pipeline — no
manual `kubectl apply` outside the pipeline.

**Q: How do you keep the chart and images in sync?**
One `image.registry`+`image.tag` for every component in the chart, and
`scripts/release.sh` refuses to release if `Chart.yaml`'s `appVersion` doesn't
match `release/version.txt`.

## Python / Bash

**Q: How do you manage Python dependencies at scale?**
One `requirements.in` of direct deps, compiled to a fully pinned lock with
hashes, one lock for the whole monorepo so no two services disagree, and a CI
test that fails if the lock drifts from the input. BUILD files say
`requirement("pyyaml")` — a version number never appears in a BUILD file.

**Q: Why is the tag logic a pure function with unit tests?**
Because tagging is the part of a release pipeline that is cheap to get wrong and
expensive to get wrong — a bad `latest` reaches every customer. `compute_tags`
has no I/O, so it is tested in milliseconds without a registry
(`tools/release/release_test.py`).

**Q: Your bash standards?**
`set -euo pipefail` at the top of every script, quoted expansions, `${VAR:?msg}`
for required arguments, no logic in CI YAML so the same script runs locally, and
`--dry-run` on anything that mutates the world.

## Honest limitations (say these before you're asked)

* Python only. Go/Rust would be added the same way, but they are not here.
* The RBE and remote-cache endpoints in `.bazelrc` are illustrative — the flags
  and the platform definition are real, the backends are not provisioned.
* Images use `python:3.11-slim` rather than distroless because of the
  `#!/usr/bin/env python3` launcher; going distroless means changing the
  bootstrap strategy.
* The demo registry is a local `registry:2`, and the smoke test reaches the
  cluster over a NodePort — in production that would be an internal LB/Ingress.
