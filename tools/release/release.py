#!/usr/bin/env python3
"""Manifest-driven multi-image release tool.

This is the piece the CI pipeline calls. CircleCI knows *nothing* about which
services exist - it only knows "run the release tool in mode X". The list of
images, their repositories and their versions live in release/manifest.yaml,
so shipping a new service is a manifest PR, not a CI-config PR.

Modes
  nightly   build everything from main every night, tag it with the date and
            the commit, move the floating `nightly` tag.
  release   cut the versions written in the manifest, tag `X.Y.Z`, `X.Y` and
            move `latest`.
  hotfix    ship ONE (or a few) components off a release branch: tag
            `X.Y.Z-hotfix.N`, never touch `latest`.

Examples
  # what would a nightly do?
  bazel run //tools/release -- --mode nightly --dry-run

  # build + load locally, then push to the registry
  bazel run //tools/release -- --mode release --push

  # customer hotfix for the api only
  bazel run //tools/release -- --mode hotfix --only api --hotfix-number 1 --push
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

DEFAULT_MANIFEST = "release/manifest.yaml"


# --------------------------------------------------------------------------
# Pure logic (unit tested in release_test.py - no docker, no network needed)
# --------------------------------------------------------------------------
def compute_tags(mode: str, version: str, date: str, sha: str, hotfix_number: int = 0) -> list[str]:
    """Return the list of tags a given release mode publishes.

    Every mode publishes at least one immutable tag that identifies exactly
    one build. Floating tags (`nightly`, `latest`) are always *additional*, so
    a rollback is always "pin the immutable tag".
    """
    short_sha = sha[:7]
    if mode == "nightly":
        return [f"nightly-{date}-{short_sha}", "nightly"]
    if mode == "release":
        major, minor, _patch = version.split(".")
        return [version, f"{major}.{minor}", "latest"]
    if mode == "hotfix":
        if hotfix_number < 1:
            raise ValueError("hotfix mode needs --hotfix-number >= 1")
        # No floating tag: a hotfix goes to the customer that asked for it and
        # must not silently become everyone's `latest`.
        return [f"{version}-hotfix.{hotfix_number}"]
    raise ValueError(f"unknown mode: {mode}")


def select_images(manifest: dict, only: list[str] | None) -> list[dict]:
    images = manifest.get("images", [])
    if not only:
        return images
    by_name = {img["name"]: img for img in images}
    missing = [n for n in only if n not in by_name]
    if missing:
        raise SystemExit(f"unknown image(s) in --only: {', '.join(missing)}")
    return [by_name[n] for n in only]


def remote_ref(manifest: dict, image: dict, registry: str | None) -> str:
    """Full repository path: <registry prefix>/<repository>.

    The prefix carries host + project path, which is what makes the same
    manifest work for GAR (europe-west1-docker.pkg.dev/acme-prod/platform),
    JFrog (acme.jfrog.io/platform-docker-local) and a customer's own registry
    during a hotfix - only --registry changes.
    """
    base = (registry or manifest["registry"]["default"]).rstrip("/")
    return f"{base}/{image['repository']}"


# --------------------------------------------------------------------------
# Shell-out helpers
# --------------------------------------------------------------------------
def run(cmd: list[str], dry_run: bool = False, capture: bool = False) -> str:
    printable = " ".join(cmd)
    print(f"+ {printable}", flush=True)
    if dry_run:
        return ""
    if capture:
        out = subprocess.run(cmd, check=True, text=True, capture_output=True)
        return out.stdout.strip()
    subprocess.run(cmd, check=True)
    return ""


def git_sha() -> str:
    for env in ("CIRCLE_SHA1", "GIT_COMMIT"):
        if os.environ.get(env):
            return os.environ[env]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "0000000nogit"


def pick_push_tool(preferred: str) -> str:
    """crane if available (no docker daemon needed), else docker."""
    if preferred != "auto":
        return preferred
    return "crane" if shutil.which("crane") else "docker"


def publish(local_ref: str, remote: str, tags: list[str], tool: str, dry_run: bool) -> str:
    """Push one local image under every tag; return its registry digest."""
    first = f"{remote}:{tags[0]}"
    if tool == "crane":
        # crane talks to the registry over plain HTTP(S) - it needs no docker
        # daemon, and `crane tag` is a metadata-only call, so the extra tags
        # cost one API request instead of re-uploading every layer.
        tarball = "/tmp/_release_image.tar"
        run(["docker", "save", "-o", tarball, local_ref], dry_run)
        run(["crane", "push", tarball, first], dry_run)
        for tag in tags[1:]:
            run(["crane", "tag", first, tag], dry_run)
        digest = run(["crane", "digest", first], dry_run, capture=True)
    else:
        for tag in tags:
            run(["docker", "tag", local_ref, f"{remote}:{tag}"], dry_run)
            run(["docker", "push", f"{remote}:{tag}"], dry_run)
        digest = run(
            ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", f"{remote}:{tags[0]}"],
            dry_run,
            capture=True,
        )
    return digest or "sha256:<dry-run>"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release", description=__doc__)
    parser.add_argument("--mode", required=True, choices=["nightly", "release", "hotfix"])
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--only", nargs="*", help="restrict to these image names")
    parser.add_argument("--registry", help="override the manifest registry (e.g. a customer GAR)")
    parser.add_argument("--hotfix-number", type=int, default=0)
    parser.add_argument("--date", default=os.environ.get("RELEASE_DATE", ""))
    parser.add_argument("--push", action="store_true", help="actually push to the registry")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    parser.add_argument("--bazel", default=os.environ.get("BAZEL", "bazel"))
    parser.add_argument("--push-tool", default="auto", choices=["auto", "crane", "docker"])
    parser.add_argument("--report", default="", help="write a JSON release report here")
    args = parser.parse_args(argv)

    # `bazel run` executes in a sandboxed runfiles dir; BUILD_WORKSPACE_DIRECTORY
    # is the real repo root, which is where the manifest and the build live.
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if workspace:
        os.chdir(workspace)

    manifest = yaml.safe_load(Path(args.manifest).read_text())
    images = select_images(manifest, args.only)
    sha = git_sha()
    date = args.date or subprocess.run(
        ["date", "-u", "+%Y%m%d"], check=True, text=True, capture_output=True
    ).stdout.strip()

    tool = pick_push_tool(args.push_tool)
    print(
        f"== release mode={args.mode} images={[i['name'] for i in images]} "
        f"sha={sha[:7]} date={date} push={args.push} tool={tool}",
        flush=True,
    )

    results = []
    for image in images:
        tags = compute_tags(args.mode, image["version"], date, sha, args.hotfix_number)
        remote = remote_ref(manifest, image, args.registry)
        print(f"\n-- {image['name']}: {remote} -> {tags}", flush=True)

        # 1. Build the image with Bazel (cache hit => nearly free).
        run([args.bazel, "build", image["target"]], args.dry_run)
        # 2. Load it into the local docker daemon as <repo>:local.
        run([args.bazel, "run", image["tarball"]], args.dry_run)
        local_ref = f"{remote}:local"

        digest = ""
        if args.push:
            digest = publish(local_ref, remote, tags, tool, args.dry_run)
        else:
            print("   (skipping push: pass --push)", flush=True)

        results.append(
            {
                "name": image["name"],
                "repository": remote,
                "tags": tags,
                "digest": digest,
                "smoke": image.get("smoke", False),
            }
        )

    report = {
        "mode": args.mode,
        "commit": sha,
        "date": date,
        "pushed": args.push and not args.dry_run,
        "images": results,
    }
    print("\n== release report ==")
    print(json.dumps(report, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(f"report written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
