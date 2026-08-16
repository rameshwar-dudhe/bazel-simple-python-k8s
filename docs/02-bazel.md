# 02 — Bazel: the parts an interviewer will ask about

## The build graph in this repo

```
release/version.txt
        │  (genrule //libs/version:gen_version)
        ▼
   version.py ──► //libs/version ──► //libs/greeter ──┬──► //services/api  ──► :image ──► :image_tarball / :image_push
                                                      └──► //services/worker ──► :image ──► ...

third_party/python/requirements_lock.txt ──► @pypi//... ──► //tools/release, //tests/smoke
```

Prove it instead of describing it:

```bash
bazel query 'rdeps(//..., //release:version.txt)' --output=label   # blast radius of a version bump
bazel query 'deps(//services/api:image)' --output=label | head     # what actually ships
bazel query 'somepath(//services/api, //libs/version)'             # why does api depend on this?
```

## bzlmod (`MODULE.bazel`)

* `bazel_dep(...)` replaces the old `WORKSPACE` + `http_archive` boilerplate;
  Bazel resolves versions from the Bazel Central Registry.
* **`MODULE.bazel.lock` is committed.** That is what makes CI resolve the exact
  same external dependency graph as a laptop. If it is not committed, "works on
  my machine" comes back.
* Module extensions used here: `python.toolchain` (hermetic CPython 3.11),
  `pip.parse` (PyPI hub `@pypi`), `oci.pull` (base image).
* `rules_python_config.explicit_init_py(default = True)` — every package ships a
  real `__init__.py`, so what runs under `bazel test` is what runs under
  `python -m`.

**Hermeticity:** the build does not use the machine's `python3`. Bazel downloads
its own interpreter. That is why `bazel test //...` gives the same result on a
CircleCI container and on a laptop.

## Dependency management (the "large scale projects" bullet)

```
third_party/python/requirements.in        # direct deps only, human-edited
third_party/python/requirements_lock.txt  # full transitive closure + sha256 hashes
```

```bash
bazel run  //third_party/python:requirements.update   # regenerate the lock
bazel test //third_party/python:requirements.test     # CI guard: lock in sync?
```

Why one lock for the whole monorepo: two services can never end up on two
different versions of the same library, so "upgrade requests" is one PR with one
blast radius instead of a scavenger hunt. In a BUILD file a dep is
`requirement("pyyaml")`, so the version is never written in a BUILD file at all.

Supply chain: the lock carries `--hash=sha256:...` for every wheel, so a
tampered or re-uploaded artifact fails the build instead of shipping.

## Caching — and why it fails in CI

Three layers, cheapest first:

1. **Action cache / analysis cache** — in-memory, same bazel server.
2. **`--disk_cache`** (in `.bazelrc`) — survives between invocations on one machine; in CI this is what `save_cache`/`restore_cache` persists.
3. **`--remote_cache`** (`--config=remotecache`) — shared across all machines. `--remote_local_fallback` means a cache outage slows the build instead of breaking it.

The two classic bugs:

* **Leaky action environment.** If `$PATH`/`$USER`/timestamps leak into actions,
  cache keys differ per machine and the remote cache never hits.
  → `build --incompatible_strict_action_env` (in `.bazelrc`).
* **Non-reproducible outputs.** Tar/image layers with real timestamps produce a
  new digest every build. → `portable_mtime = True`, `owner = "0.0"` in
  `tools/bazel/py_image.bzl`, so an unchanged service pushes nothing new.

PR builds use `--config=remotecache_ro` (`--remote_upload_local_results=false`)
so an untrusted PR can read the cache but never write to it.

## RBE (Remote Build Execution)

`--config=rbe` in `.bazelrc`:

```
--remote_executor=grpcs://...   run actions on the RBE cluster, not the executor
--jobs=100                      a 2-vCPU CI container can drive 100 parallel actions
--platforms=//platforms:rbe_linux_amd64
--remote_download_toplevel      only fetch the outputs you actually asked for
--bes_backend / --bes_results_url  a shareable invocation URL for every build
```

`platforms/BUILD.bazel` pins the RBE worker container image in
`exec_properties`, so changing the worker image correctly invalidates every
remotely executed action instead of silently reusing stale results.

Two things to mention as the real-world RBE pain points:
1. **Toolchain hermeticity** — anything not declared (a system compiler, a local
   python) works locally and fails on RBE. Hermetic toolchains fix it.
2. **Big inputs / big outputs** — RBE is a network. `--remote_download_toplevel`
   and avoiding giant runfiles trees is most of the tuning.

## Troubleshooting toolkit

| symptom | command |
|---|---|
| why is this target rebuilding? | `bazel build //x --explain=explain.log --verbose_explanations` |
| what commands does it actually run? | `bazel aquery 'deps(//services/api:image)'` |
| why does A depend on B? | `bazel query 'somepath(//A, //B)'` |
| what does a change break? | `bazel query 'rdeps(//..., //libs/greeter)'` |
| flaky/slow tests | `--runs_per_test=20`, `--test_output=all`, JUnit XML in `bazel-testlogs/` |
| clean-room reproduction | `bazel clean --expunge` (last resort — it throws away all caches) |
| where did this external dep come from? | `bazel mod graph`, `bazel mod explain @rules_python` |

## Images from Bazel (`tools/bazel/py_image.bzl`)

One macro, both services:

```
pkg_tar(include_runfiles) ──► oci_image(base = @python_base, entrypoint = /app/<bin>)
                                 ├─► oci_load  → docker daemon (:local)
                                 └─► oci_push  → registry
```

Two design decisions worth defending:

* **Base pinned by digest** in `MODULE.bazel`. A tag like `3.11-slim` is mutable;
  a digest is not. Bumping it is a deliberate PR.
* **`python:3.11-slim` rather than distroless** — the `py_binary` launcher
  rules_python generates starts with `#!/usr/bin/env python3`, and distroless
  has neither `/usr/bin/env` nor a shell. The app code and wheels still come
  from Bazel's runfiles; only the interpreter comes from the base. To go
  distroless you switch the bootstrap to a zip/self-contained launcher — call
  that out as the trade-off you knowingly took.

## Known noise

`bazel build` prints a deprecation warning about implicit `__init__.py` creation
for `@rules_pkg//pkg/private/tar:build_tar`. That is an upstream rules_pkg
target, not this repo's code — worth recognising so it doesn't surprise you.
