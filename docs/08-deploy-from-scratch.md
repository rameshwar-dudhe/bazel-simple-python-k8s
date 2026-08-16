# 08 — Teardown and deploy from scratch

The exact procedure to wipe everything this repo deployed and bring it back up.
Every command and every output below was executed on 2026-08-16 against a real
2-node Kubernetes 1.36 cluster, a local `registry:2`, and Bazel 9.2.0 — the
outputs are copied from that run, not written from memory.

Total time from a clean machine: **~2 minutes** (about 6 minutes if the Bazel
disk cache is also cold).

---

## 0. Prerequisites

```bash
bazel --version      # 9.2.0 (or bazelisk — .bazelversion pins it)
docker info          # a running daemon
kubectl cluster-info # a reachable cluster
helm version --short # v3.x
crane version        # optional; the release tool falls back to docker
```

Install crane if it is missing (this is what CI's `install_crane` command does):

```bash
curl -fsSL "https://github.com/google/go-containerregistry/releases/download/v0.20.2/go-containerregistry_Linux_x86_64.tar.gz" \
  | sudo tar -xz -C /usr/local/bin crane
```

A demo registry, if you do not already have one:

```bash
docker run -d -p 5000:5000 --restart=always --name registry registry:2
```

**The one thing people get wrong:** the cluster nodes pull the images, not your
laptop. `localhost:5000` means "localhost *on the node*". Use an address the
nodes can reach — in this environment `192.168.56.133:5000` (the host's LAN IP),
which the nodes' containerd already trusts as an insecure registry. Check with:

```bash
hostname -I | awk '{print $1}'                     # 192.168.56.133
kubectl get nodes -o wide                          # nodes are .134 / .135
curl -s http://192.168.56.133:5000/v2/_catalog     # reachable?
```

---

## 1. Teardown — remove everything

```bash
scripts/teardown.sh
```

It touches only what this repo created: the Helm release, its namespace, local
`*/pyplatform/*` docker images, the `pyplatform/*` registry repositories, and
local build outputs (`bazel clean`, `dist/`, `release-report.json`). It is
idempotent — running it twice is fine.

```
==> 1/5 helm release
release "pyplatform" uninstalled

==> 2/5 namespace
namespace "pyplatform" deleted

==> 3/5 local docker images
    removed localhost:5000/pyplatform/api:local
    removed localhost:5000/pyplatform/worker:local

==> 4/5 registry repositories (192.168.56.133:5000)
    pyplatform/api:latest - registry refused DELETE (deletion disabled); will be overwritten on next push
    pyplatform/worker:latest - registry refused DELETE (deletion disabled); will be overwritten on next push

==> 5/5 local build outputs
INFO: Starting clean (this may take a while)...

OK - teardown complete.
```

> **Note on step 4.** A `registry:2` container only honours `DELETE` when it was
> started with `REGISTRY_STORAGE_DELETE_ENABLED=true`, and even then the blobs
> only disappear after `registry garbage-collect`. This one has deletion
> disabled, so the old manifests stay until the next push overwrites the tags.
> Real registries (GAR, JFrog) do this with **retention/cleanup policies**
> instead of ad-hoc deletes — e.g. "keep the last 10 `nightly-*`, keep all
> semver tags forever". Say that in an interview rather than "I delete tags by
> hand".

Options:

```bash
KEEP_BAZEL_CACHE=1 scripts/teardown.sh   # skip bazel clean → faster redeploy
NAMESPACE=pyplatform-staging scripts/teardown.sh
```

Confirm it is gone:

```bash
kubectl get ns | grep pyplatform     # (no output)
docker images | grep pyplatform      # (no output)
ls bazel-bin                         # No such file or directory
```

---

## 2. Build and test

```bash
bazel test //...
```
```
INFO: Found 37 targets and 4 test targets...
INFO: 144 processes: 30 disk cache hit, 118 internal.
Executed 0 out of 4 tests: 4 tests pass.
```

`Executed 0 out of 4` is not a problem — the disk cache survived `bazel clean`,
so Bazel reused the cached *test results*. That is the point of the cache. To
force real execution (e.g. when demoing):

```bash
bazel test //... --nocache_test_results
```

---

## 3. Build the container images

```bash
make image        # = bazel run //services/api:image_tarball + worker
```
```
Loaded image: localhost:5000/pyplatform/api:local
Loaded image: localhost:5000/pyplatform/worker:local
```

Optional local sanity check before touching the cluster:

```bash
docker run --rm -p 8080:8080 localhost:5000/pyplatform/api:local
curl localhost:8080/version
# {"service": "api", "version": "1.4.0", "environment": "local"}
```

---

## 4. Release: tag and push (manifest-driven)

Always look at the plan first — this is also the best thing to show an
interviewer, because it prints the decisions without making any:

```bash
bazel run //tools/release -- --mode release --dry-run
```

Then publish. `--registry` overrides the manifest's default with an address the
**nodes** can reach:

```bash
bazel run //tools/release -- --mode release --push \
  --registry 192.168.56.133:5000/pyplatform \
  --report release-report.json
```

```json
{
  "mode": "release",
  "commit": "d9831ede2696efabdfcbd87c1ee56e422fe556a8",
  "date": "20260816",
  "pushed": true,
  "images": [
    {"name": "api",    "repository": "192.168.56.133:5000/pyplatform/api",
     "tags": ["1.4.0", "1.4", "latest"],
     "digest": "sha256:a5b214e9376373282859b77407e47086164a66682c8b53c0563752f4ed01328a", "smoke": true},
    {"name": "worker", "repository": "192.168.56.133:5000/pyplatform/worker",
     "tags": ["1.4.0", "1.4", "latest"],
     "digest": "sha256:cc2e00110228bc6aa51d3cae960b6bdcbc981956b024a17a51897a9975ecc115", "smoke": false}
  ]
}
```

**Worth noticing:** these digests are byte-for-byte the same as the run before
the teardown. Reproducible layers (`portable_mtime`, fixed ownership in
`tools/bazel/py_image.bzl`) mean a rebuild of unchanged code produces an
identical image — so a re-release uploads nothing new.

`scripts/release.sh release` is the CI entry point; it wraps the same command,
adds the `Chart.yaml appVersion == version.txt` guard, and pushes the Helm
chart. Use the raw `bazel run` above when you want a different `--registry`
without editing anything.

Verify what landed:

```bash
curl -s http://192.168.56.133:5000/v2/pyplatform/api/tags/list
# {"name":"pyplatform/api","tags":["latest","1.4","1.4.0"]}
crane digest 192.168.56.133:5000/pyplatform/api:1.4.0
```

---

## 5. Deploy with Helm

```bash
scripts/deploy.sh 1.4.0            # scripts/deploy.sh <tag> [namespace]
```

The script lints the chart, runs `helm upgrade --install ... --wait`, then waits
on `kubectl rollout status`. It defaults `image.registry` to
`<host-ip>:5000/pyplatform`; override with `REGISTRY=...`.

```
==> helm lint
1 chart(s) linted, 0 chart(s) failed
==> deploying 192.168.56.133:5000/pyplatform/{api,worker}:1.4.0 to ns/pyplatform
Release "pyplatform" does not exist. Installing it now.
==> rollout status
deployment "pyplatform-pyplatform-api" successfully rolled out

NAME                                        READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/pyplatform-pyplatform-api   2/2     2            2           8s
pod/pyplatform-pyplatform-api-54876f9dc9-7wm7j   1/1   Running   0   8s
pod/pyplatform-pyplatform-api-54876f9dc9-b84k2   1/1   Running   0   8s
service/pyplatform-pyplatform-api   NodePort   10.97.143.248   80:30081/TCP   8s
cronjob.batch/pyplatform-pyplatform-worker   */15 * * * *   False   0   8s
OK
```

Deploy somewhere else, or with a different tag:

```bash
scripts/deploy.sh nightly-20260816-d9831ed pyplatform-staging
APP_ENV=staging RELEASE_NAME=pyplatform scripts/deploy.sh 1.4.0 pyplatform-staging
```

---

## 6. Smoke validation

```bash
scripts/smoke.sh 1.4.0
```
```
==> smoke testing http://192.168.56.134:30081 (expecting version 1.4.0)
Ran 3 tests in 0.020s
OK
```

The script resolves the node IP and NodePort from the cluster itself, then
asserts health, **deployed version == the tag we just released**, and one real
endpoint.

---

## 7. Verify by hand

```bash
curl -s http://192.168.56.134:30081/version
# {"service": "api", "version": "1.4.0", "environment": "dev"}
curl -s "http://192.168.56.134:30081/greet?name=vikrant"
# {"message": "hello, vikrant!"}
```

The worker only runs every 15 minutes; trigger it now to prove the second image
works too:

```bash
kubectl -n pyplatform create job --from=cronjob/pyplatform-pyplatform-worker w1
kubectl -n pyplatform logs job/w1
```
```
{"msg": "batch start", "batch": 5, "service": "worker", "version": "1.4.0", "environment": "dev"}
{"item": "job-1", "message": "hello, job-1!"}
...
{"msg": "batch done", "service": "worker", "version": "1.4.0", "environment": "dev"}
kubectl -n pyplatform delete job w1     # tidy up
```

---

## The whole thing, copy-pasteable

```bash
scripts/teardown.sh
bazel test //...
make image
bazel run //tools/release -- --mode release --push \
  --registry "$(hostname -I | awk '{print $1}'):5000/pyplatform" \
  --report release-report.json
scripts/deploy.sh 1.4.0
scripts/smoke.sh 1.4.0
```

Or, once the images are published, just:

```bash
make deploy TAG=1.4.0 && make smoke TAG=1.4.0
```

---

## Rollback

```bash
helm -n pyplatform history pyplatform
helm -n pyplatform rollback pyplatform 1      # chart + values revert
scripts/deploy.sh 1.3.0                       # code revert (previous immutable tag)
```

Which one to reach for: `helm rollback` when the *chart or values* changed,
redeploy the previous immutable tag when the *application* is broken. This is
why the pipeline never deploys `latest` — you cannot roll back to a tag that
moves.

---

## Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `nodePort: provided port is already allocated` | another service owns 30081 | `helm ... --set api.service.nodePort=30082`, or change `values.yaml` |
| pods stuck `ImagePullBackOff` | `image.registry` not reachable from the **nodes** (e.g. `localhost:5000`), or the registry isn't in containerd's insecure-registry list | push to the host LAN IP and use the same value in `--set image.registry` |
| `ErrImagePull … x509` / `http: server gave HTTP response to HTTPS client` | node's containerd wants TLS | add the registry under `[plugins."io.containerd.grpc.v1.cri".registry]` on each node, or use a TLS registry |
| smoke fails on the version assertion | cluster still serving the old image | `kubectl -n pyplatform get pod -o jsonpath='{..image}'` — check the tag actually rolled |
| `helm upgrade` times out | pods never became Ready | `kubectl -n pyplatform describe pod <name>` and `logs`; the readiness probe hits `/readyz` |
| release tool can't find the manifest | run it through Bazel — it uses `BUILD_WORKSPACE_DIRECTORY` | `bazel run //tools/release -- …`, not the binary in `bazel-bin` |
| `crane` not found | not installed | the tool automatically falls back to `docker tag`/`docker push` |
| deprecation warning about implicit `__init__.py` | comes from `@rules_pkg`, not this repo | ignore |
