# 03 — CircleCI: `.circleci/config.yml` explained

Validated with the real CLI:

```bash
circleci config validate .circleci/config.yml
# Config file at .circleci/config.yml is valid.
```

## The five workflows, and what triggers each

| workflow | trigger | does |
|---|---|---|
| `pr` | any branch that is not `main` | `lint` → `build_and_test` (cache **read-only**). Publishes nothing. |
| `main` | push to `main` | lint → build/test (cache read-write) → publish date+sha tags → deploy dev → smoke |
| `nightly` | scheduled pipeline setting `run_nightly=true` | full build/test → publish `nightly-<date>-<sha>` + `nightly` → deploy staging → smoke |
| `release` | git tag matching `^v\d+\.\d+\.\d+$` | build/test → publish `1.4.0`/`1.4`/`latest` + chart → staging + smoke → **manual approval** → prod |
| `hotfix` | API trigger with `run_hotfix=true` + parameters | build/test → approval → publish ONE component to a customer registry |

All five live in one config. The switch is `when:` on **pipeline parameters**
(`run_nightly`, `run_hotfix`) and on `pipeline.git.branch`. This is the modern
replacement for the deprecated `triggers: schedule:` block, and the reason it is
better: a scheduled pipeline can carry parameters, so nightly reuses the exact
same jobs instead of a forked copy of them.

Setting up the nightly in the UI: *Project Settings → Triggers → Schedule*,
cron `0 2 * * 1-5`, branch `main`, parameter `run_nightly: true`.

Triggering a hotfix from the API:

```bash
curl -X POST https://circleci.com/api/v2/project/gh/acme/pyplatform/pipeline \
  -H "Circle-Token: $CIRCLE_TOKEN" -H 'content-type: application/json' \
  -d '{"branch":"release/1.4",
       "parameters":{"run_hotfix":true,"hotfix_component":"api",
                     "hotfix_number":1,
                     "hotfix_registry":"customer-a.jfrog.io/platform"}}'
```

## Reusable pieces (the "orbs/commands" bullet)

* **`orbs:`** — `circleci/gcp-cli` (gcloud + OIDC auth), `circleci/slack`
  (failure notifications). Versioned, so upgrades are a one-line diff.
* **`commands:`** — this repo's own reusable steps: `setup_bazel`,
  `restore_bazel_cache`, `save_bazel_cache`, `auth_gar`, `install_crane`,
  `notify_failure`. If these were shared across repos, you would publish them as
  a private orb in your org's registry — same YAML, different home.
* **`executors:`** — `bazel` (large) and `deployer` (`cimg/deploy`, has
  kubectl+helm). One place to bump images.
* **parameterised jobs** — `publish` takes `mode`, `component`,
  `hotfix_number`, `registry`; `build_and_test` takes `cache_mode`;
  `deploy_and_smoke` takes `environment` + `namespace`. Four jobs cover five
  workflows.
* **YAML anchors** — `&release_filters` / `*release_filters` declares the tag
  filter once.

## Speed: what actually makes it fast

1. **Bazel remote cache** — the real win. Unchanged targets are not rebuilt at
   all. `remotecache` (rw) on main/nightly/release, `remotecache_ro` on PRs.
2. **`restore_cache` key design** —
   `bazel-v3-{{ checksum "MODULE.bazel.lock" }}-{{ checksum "requirements_lock.txt" }}`
   with progressively shorter fallback keys. The key is derived from the files
   that *actually* invalidate the cache, so an ordinary source edit still gets a
   warm cache. The `v3` prefix is the manual escape hatch when a cache goes bad.
3. **Fail cheap first** — `lint` (~1 min) gates `build_and_test`.
4. **Do the work once** — `publish` writes `release-report.json`,
   `persist_to_workspace` hands it to `deploy_and_smoke`, which reads the tag
   from it instead of recomputing (and possibly disagreeing).
5. **`docker_layer_caching` + `setup_remote_docker`** only in the job that needs
   a daemon.
6. **`store_test_results`** with Bazel's JUnit XML — CircleCI's test insights
   then show which tests are slow or flaky, which is how you decide what to fix.

Deliberately *not* used: `parallelism: N` with test splitting. Bazel already
parallelises within one executor and skips unchanged tests; splitting a Bazel
suite across containers usually buys less than the cache does. Say that out
loud — knowing when *not* to shard is a senior answer.

## Safety

* PRs never publish and never write to the shared cache.
* Registry/cluster credentials come from **contexts**
  (`gcp-artifact-registry`, `gke-dev/staging/prod`, `customer-registries`),
  which are restricted to the right branches/teams — not from project env vars.
* GAR auth is **OIDC / Workload Identity Federation** (`gcp-cli/setup:
  use_oidc: true`), so there is no long-lived service-account JSON key in
  CircleCI.
* Production needs a human: `hold_for_production` is an `approval` job.
* `deploy_and_smoke` has a `when: on_fail` step that runs `helm rollback`.

## Porting to Jenkins / GitLab (the "other CI tools" bullet)

Every job body is `scripts/<something>.sh`. A GitLab port is:

```yaml
build_and_test:
  script: [BAZEL_CONFIGS="--config=ci --config=remotecache" scripts/ci-build.sh]
```

and a Jenkinsfile stage is the same one-liner. Only the wiring — caching syntax,
credentials, triggers — is CI-specific. That is the whole reason the logic lives
in scripts instead of in YAML.
