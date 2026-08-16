# 04 — Releases, registries, crane, hotfixes

## The idea in one line

**CI does not know what a release contains.** `release/manifest.yaml` does.

```yaml
registry:
  default: localhost:5000/pyplatform     # GAR / JFrog prefix in real life
  local:   localhost:5000/pyplatform     # what `oci_load` tags locally
images:
  - name: api
    target:  //services/api:image
    tarball: //services/api:image_tarball
    repository: api
    version: 1.4.0
    smoke: true
  - name: worker
    ...
charts:
  - name: pyplatform
    path: deploy/helm/pyapp
    version: 0.3.0
```

Adding a third service to the release = 6 lines of YAML. No CI change.
`release/version.txt` is the monorepo version and also feeds the build graph
(`//libs/version`), so the version an image *reports at runtime* and the version
it is *tagged with* cannot drift.

## Tag strategy

| mode | tags published | notes |
|---|---|---|
| `nightly` | `nightly-20260816-abc1234`, `nightly` | immutable + floating |
| `release` | `1.4.0`, `1.4`, `latest` | immutable + two floating |
| `hotfix` | `1.4.0-hotfix.1` | **never** touches `latest` |

Rules the code enforces (`tools/release/release.py:compute_tags`, unit tested in
`release_test.py`):

1. Every mode publishes **at least one immutable tag** that identifies exactly
   one build → a rollback is always "pin the immutable tag".
2. Floating tags are always *additional*, never the only tag.
3. Deployments use the immutable tag (`scripts/deploy.sh` takes it as an
   argument; the CI job reads it from `release-report.json`). Never deploy
   `latest` — you cannot roll back to a tag that moves.

## Running it

```bash
bazel run //tools/release -- --mode nightly --dry-run     # plan only, no side effects
scripts/release.sh release                                 # build + push everything
scripts/release.sh hotfix api 1                            # one component, hotfix tag
REGISTRY=customer-a.jfrog.io/platform scripts/release.sh hotfix api 1
```

Output (`release-report.json`, also stored as a CI artifact):

```json
{
  "mode": "release", "commit": "8d4d860...", "date": "20260816", "pushed": true,
  "images": [
    {"name": "api", "repository": "localhost:5000/pyplatform/api",
     "tags": ["1.4.0", "1.4", "latest"],
     "digest": "sha256:a5b214e93763...", "smoke": true},
    {"name": "worker", "...": "..."}
  ]
}
```

The digest is the point: everything downstream (deploy, smoke, an audit trail,
a customer support ticket) can refer to an immutable reference.

## Why crane

`tools/release/release.py:publish()` prefers `crane`, falls back to `docker`.

* **No docker daemon needed.** crane speaks the registry API directly, so the CI
  job doesn't need `setup_remote_docker` just to move bits.
* **Re-tagging is a metadata call.** `crane tag repo:1.4.0 latest` costs one API
  request; `docker tag && docker push` re-resolves and re-verifies layers.
* Other things it does that come up in this job:
  `crane copy` (promote staging→prod, or mirror to a customer registry, without
  pulling), `crane digest`, `crane ls`, `crane manifest`, `crane index` for
  multi-arch, `crane cp` between GAR and JFrog.

## GAR and JFrog

The manifest holds a *prefix*, so the same tool targets any registry:

| registry | prefix |
|---|---|
| Google Artifact Registry | `europe-west1-docker.pkg.dev/acme-prod/platform` |
| JFrog Artifactory | `acme.jfrog.io/platform-docker-local` |
| local demo | `localhost:5000/pyplatform` |
| customer hotfix | `--registry customer-a.jfrog.io/platform` |

Auth in CI (`.circleci/config.yml` → `auth_gar`): the `gcp-cli` orb with
`use_oidc: true` (Workload Identity Federation) → `gcloud auth
configure-docker` → `crane auth login` with a short-lived access token. **No
service-account JSON key stored in CircleCI.** For JFrog the equivalent is a
scoped access token in a context, `crane auth login acme.jfrog.io`.

Registry hygiene worth mentioning: immutable tags on release repos, cleanup
policies for `nightly-*` older than N days, and vulnerability scanning on push
(GAR Artifact Analysis / JFrog Xray).

## Helm charts as artifacts

`scripts/release.sh` packages and pushes the chart to the *same* registry as an
OCI artifact:

```bash
helm package deploy/helm/pyapp --destination dist/
helm push dist/pyplatform-0.3.0.tgz oci://<registry>/charts
```

Both GAR and JFrog store OCI Helm charts natively, so charts and images share
auth, retention and scanning. The chart's `appVersion` must equal
`release/version.txt` — `scripts/release.sh` fails the release if it doesn't.

## Hotfix delivery to a customer

1. Branch `release/1.4` (the released code, not `main`).
2. Cherry-pick the fix, bump nothing — the hotfix number carries the identity.
3. Trigger the `hotfix` pipeline with `hotfix_component=api`,
   `hotfix_number=1`, `hotfix_registry=customer-a.jfrog.io/platform`.
4. A human approves (`hold_for_hotfix`).
5. The tool builds **only** that component, tags `1.4.0-hotfix.1`, pushes to the
   customer's registry, and leaves `latest` alone.
6. The release report is the artifact you attach to the support ticket.

Why one component and not the whole set: less to re-qualify at the customer, and
the manifest still records exactly which other components they are running.
