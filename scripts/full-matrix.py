#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


def main():
    target = os.environ.get("REQUESTED_TARGET") or "all"
    event = os.environ["GITHUB_EVENT_NAME"]
    lock_file = Path(__file__).resolve().parents[1] / "build-aux/toolchains.tsv"
    images = dict(line.split("\t") for line in lock_file.read_text().splitlines())
    if target not in {"all", "macos-arm64", *images}:
        sys.exit(f"Unknown Full target {target!r}")

    macos = target in {"all", "macos-arm64"}
    if event in {"push", "pull_request"}:
        macos = False
        targets = [
            "x86_64-unknown-linux-musl",
            "aarch64-unknown-linux-musl",
            "x86_64-w64-mingw32",
        ]
    elif target == "all":
        targets = list(images)
    elif target == "macos-arm64":
        targets = []
    else:
        targets = [target]

    matrix = [
        {"target": platform, "image": images[platform]} for platform in targets
    ]
    artifact_targets = targets + (["macos-arm64"] if macos else [])
    print("static_matrix=" + json.dumps({"include": matrix}))
    print("has_static=" + str(bool(matrix)).lower())
    print("has_macos=" + str(macos).lower())
    print("artifact_targets=" + " ".join(artifact_targets))


if __name__ == "__main__":
    main()
