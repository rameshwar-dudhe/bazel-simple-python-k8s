"""A second deployable that shares //libs/greeter with the API.

Why a second service exists in this repo: the release pipeline is
*multi-image* and manifest-driven. One service would never show that
`release/manifest.yaml` - not the CI config - decides what gets built,
tagged and pushed.

Run: bazel run //services/worker -- --batch 3
"""

import argparse
import json
import os
import sys
import time

from libs.greeter import greeter

SERVICE_NAME = "worker"


def process_batch(size: int, names: list[str] | None = None) -> list[dict]:
    """Pretend work: emit one record per item in the batch."""
    names = names or [f"job-{i}" for i in range(1, size + 1)]
    return [{"item": n, "message": greeter.greet(n)} for n in names[:size]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="worker")
    parser.add_argument("--batch", type=int, default=int(os.environ.get("BATCH_SIZE", "5")))
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds between records")
    args = parser.parse_args(argv)

    info = greeter.build_info(SERVICE_NAME, os.environ.get("APP_ENV", "local"))
    print(json.dumps({"msg": "batch start", "batch": args.batch, **info}), flush=True)

    for record in process_batch(args.batch):
        print(json.dumps(record), flush=True)
        if args.sleep:
            time.sleep(args.sleep)

    print(json.dumps({"msg": "batch done", **info}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
