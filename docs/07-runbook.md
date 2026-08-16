# 07 — Runbook: every command, with what you should see

Prerequisites: `bazel` (or bazelisk — `.bazelversion` pins 9.2.0), `docker`,
`helm`, `kubectl`, and for the release demo a registry (`docker run -d -p 5000:5000
--name registry registry:2`) plus a cluster. Steps 1–4 need none of that.

## 1. Tests (hermetic — no docker, no cluster, no network after the first fetch)

```bash
bazel test //...
```
```
Executed 4 out of 4 tests: 4 tests pass.
```

The four: `//libs/greeter:greeter_test`, `//services/api:app_test`,
`//services/worker:worker_test`, `//tools/release:release_test`.
`//tests/smoke:smoke_test` is `manual` on purpose — it needs a cluster.

## 2. Run the services locally

```bash
bazel run //services/api          # then: curl 'localhost:8080/greet?name=you'
bazel run //services/worker -- --batch 3
```

## 3. Look at the build graph

```bash
make graph
# bazel query 'rdeps(//..., //release:version.txt)' --output=label
```
Everything downstream of the version file: the genrule, `//libs/version`,
`//libs/greeter`, both services, both images. Edit `release/version.txt`, re-run
`bazel test //...`, and watch only those targets re-run.

```bash
bazel query 'somepath(//services/api, //libs/version)'   # why this edge exists
bazel query 'deps(//services/api:image)' | wc -l         # what ships in the image
```

## 4. Dependency lock

```bash
bazel run  //third_party/python:requirements.update   # after editing requirements.in
bazel test //third_party/python:requirements.test     # CI's drift guard
```

## 5. Build container images with Bazel

```bash
make image
# bazel run //services/api:image_tarball
# -> Loaded image: localhost:5000/pyplatform/api:local
docker run --rm -p 8080:8080 localhost:5000/pyplatform/api:local
curl localhost:8080/version
# {"service": "api", "version": "1.4.0", "environment": "local"}
```

## 6. Release (manifest-driven)

```bash
bazel run //tools/release -- --mode nightly --dry-run
```
```
== release mode=nightly images=['api', 'worker'] sha=8d4d860 date=20260816 push=False tool=crane
-- api: localhost:5000/pyplatform/api -> ['nightly-20260816-8d4d860', 'nightly']
+ bazel build //services/api:image
...
```

Real push (needs a registry):

```bash
scripts/release.sh release
curl -s localhost:5000/v2/pyplatform/api/tags/list
# {"name":"pyplatform/api","tags":["latest","1.4","1.4.0"]}
cat release-report.json          # tags + digests per image
```

Hotfix into a different registry:

```bash
REGISTRY=customer-a.jfrog.io/platform scripts/release.sh hotfix api 1
# publishes only api:1.4.0-hotfix.1, leaves latest alone
```

## 7. Deploy + smoke on a cluster

```bash
# push to an address the NODES can reach (not localhost:5000)
bazel run //tools/release -- --mode release --push --registry <host-ip>:5000/pyplatform

scripts/deploy.sh 1.4.0
```
```
deployment "pyplatform-pyplatform-api" successfully rolled out
pod/pyplatform-pyplatform-api-...   1/1 Running     (x2)
service/pyplatform-pyplatform-api   NodePort  80:30081/TCP
cronjob.batch/pyplatform-pyplatform-worker  */15 * * * *
```
```bash
scripts/smoke.sh 1.4.0
# Ran 3 tests ... OK
```

Trigger a worker run immediately instead of waiting for the schedule:

```bash
kubectl -n pyplatform create job --from=cronjob/pyplatform-pyplatform-worker w1
kubectl -n pyplatform logs job/w1
```

## 8. Pre-flight checks (what the CI `lint` job runs)

```bash
scripts/lint.sh                              # bazel query, YAML, helm lint/template, bash -n
circleci config validate .circleci/config.yml
# Config file at .circleci/config.yml is valid.
```

## 9. Clean up the demo

```bash
helm -n pyplatform uninstall pyplatform
kubectl delete ns pyplatform
bazel clean
```

## Troubleshooting

| symptom | check |
|---|---|
| `nodePort: provided port is already allocated` | another service owns 30081 → `--set api.service.nodePort=` a free one |
| pods `ImagePullBackOff` | the nodes can't reach `image.registry` (don't use `localhost:5000`), or the registry is not in the nodes' insecure-registries list |
| smoke test fails on the version assertion | the cluster is still serving the old image — check `kubectl get pod -o jsonpath='{..image}'` |
| `bazel run //tools/release` can't find the manifest | run it via bazel (it uses `BUILD_WORKSPACE_DIRECTORY`), not from `bazel-bin` |
| warning about implicit `__init__.py` | comes from `@rules_pkg`, not this repo — harmless |
