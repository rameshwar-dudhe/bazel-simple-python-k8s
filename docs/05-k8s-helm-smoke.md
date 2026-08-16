# 05 — Helm, Kubernetes and smoke validation

## The chart (`deploy/helm/pyapp`)

```
Chart.yaml            version 0.3.0 (chart), appVersion 1.4.0 (default image tag)
values.yaml           image.registry / image.tag / api.* / worker.* / env.*
templates/
  _helpers.tpl        naming + labels + the pyapp.image helper
  deployment.yaml     the API: 2 replicas, split liveness/readiness probes
  service.yaml        NodePort 30081 (a stable URL for the demo smoke test)
  cronjob.yaml        the worker: same release, different workload type
  NOTES.txt           smoke + rollback commands, printed after install
```

Both images come from the same `image.registry` + `image.tag`, so the API and
the worker can never drift to different versions of the same release.

Deploying:

```bash
scripts/deploy.sh 1.4.0 pyplatform
# -> helm lint
# -> helm upgrade --install ... --set image.tag=1.4.0 --wait --timeout 3m
# -> kubectl rollout status deploy/pyplatform-pyplatform-api --timeout=120s
```

Points worth making:

* **`--set image.tag=<immutable tag>`** — the pipeline passes the tag it just
  published (read from `release-report.json`), never `latest`.
* **`--wait` + `rollout status`** — the deploy step fails if pods don't become
  Ready, instead of "succeeding" and leaving a broken release.
* **Split probes** — `/healthz` (liveness: is the process alive) and `/readyz`
  (readiness: should it get traffic). Using one endpoint for both is the classic
  mistake that turns a slow start into a crash loop.
* **`image.registry` must resolve from the cluster nodes**, not your laptop —
  `scripts/deploy.sh` defaults to the host's LAN IP for exactly that reason.
* Resource requests/limits are set: without requests the scheduler cannot make
  sane decisions and the pod is BestEffort, first to be evicted.

## Smoke validation (`tests/smoke/smoke_test.py`)

```bash
scripts/smoke.sh 1.4.0 pyplatform
```

It resolves the NodePort URL from the cluster, then asserts three things:

1. `/healthz` returns 200 — the deployment serves traffic at all.
2. **`/version` equals the tag that was just released** — the assertion that
   actually catches a bad release. A rollout can report success while the
   cluster still serves the old image (wrong tag in values, a cached `latest`,
   a failed pull with old replicas still up).
3. `/greet` behaves — one real endpoint, so "up" means "useful", not "the
   health handler works".

Design details to defend:

* **Retries with backoff** (`SMOKE_RETRIES`) — pods may still be rolling; the
  test should be resilient, not flaky.
* **`tags = ["manual", "external"]`** in the BUILD file — it never runs inside
  the hermetic `bazel test //...`, and its result is never cached (the cluster
  is the input, and Bazel cannot see it change).
* **Small and fast.** Smoke validation gates a release; if it takes 20 minutes,
  people route around it.
* On failure, the CircleCI job's `when: on_fail` step runs `helm rollback`.

## Verified run

On a real 2-node Kubernetes 1.36 cluster:

```
deployment.apps/pyplatform-pyplatform-api   2/2 Ready
service/pyplatform-pyplatform-api           NodePort 80:30081/TCP
cronjob.batch/pyplatform-pyplatform-worker  */15 * * * *
smoke: Ran 3 tests ... OK
```

## Rollback

```bash
helm -n pyplatform history pyplatform
helm -n pyplatform rollback pyplatform 3     # or: redeploy the previous immutable tag
```

Two rollback paths, and the difference matters in an interview: `helm rollback`
reverts *chart + values* (good when the template changed), redeploying the
previous image tag reverts *the code* (good when the chart is fine and the app
is broken).
