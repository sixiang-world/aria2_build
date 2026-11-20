#!/usr/bin/env python3
"""Allocate date-stamped release tags and update the Windows Scoop manifest."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import mkstemp


ARIA2_VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"
RELEASE_TAG = re.compile(rf"v{ARIA2_VERSION}-[0-9]{{8}}\.[0-9]+")
SHA256 = re.compile(r"[0-9a-f]{64}")
TRIPLES = {"64bit": "x86_64-w64-mingw32", "32bit": "i686-w64-mingw32"}
DOWNLOADS = "https://github.com/sixiang-world/aria2_build/releases/download"


def next_tag(version, remote, date):
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
    elif not re.fullmatch(r"[0-9]{8}", date):
        raise ValueError("Date must be in YYYYMMDD format")
    else:
        datetime.strptime(date, "%Y%m%d")

    prefix = f"v{version}-{date}."
    ref_prefix = f"refs/tags/{prefix}"
    sequence_pattern = re.compile(rf"{re.escape(ref_prefix)}([0-9]+)")
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "--", remote, f"{ref_prefix}*"],
        check=True, capture_output=True, text=True,
    )
    latest = 0
    for line in result.stdout.splitlines():
        match = sequence_pattern.fullmatch(line.split("\t", 1)[-1])
        if match:
            latest = max(latest, int(match[1]))
    return f"{prefix}{latest + 1}"


def read_checksums(checksums, filenames):
    hashes = {}
    for line in checksums.read_text(encoding="utf-8").splitlines():
        digest, _, entry = line.partition(" ")
        filename = entry[1:]
        if filename not in filenames or entry[:1] not in (" ", "*"):
            continue
        if not SHA256.fullmatch(digest):
            raise ValueError(f"Invalid SHA-256 for {filename}")
        if filename in hashes:
            raise ValueError(f"Duplicate SHA-256 for {filename}")
        hashes[filename] = digest

    missing = filenames - hashes.keys()
    if missing:
        raise ValueError(f"Missing SHA-256 for {', '.join(sorted(missing))}")
    return hashes


def update_manifest(tag, version, checksums, manifest):
    if not RELEASE_TAG.fullmatch(tag):
        raise ValueError(f"Invalid release tag: {tag}")

    filenames = {arch: f"aria2-{version}-{triple}_static.zip" for arch, triple in TRIPLES.items()}
    hashes = read_checksums(checksums, set(filenames.values()))
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = tag.removeprefix("v")
    for arch, filename in filenames.items():
        data["architecture"][arch].update(url=f"{DOWNLOADS}/{tag}/{filename}", hash=hashes[filename])

    fd, name = mkstemp(dir=manifest.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=4, ensure_ascii=False)
            stream.write("\n")
        shutil.copymode(manifest, temporary)
        temporary.replace(manifest)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    allocate = subcommands.add_parser("next-tag")
    allocate.add_argument("--aria2-version", required=True)
    allocate.add_argument("--remote", default="origin")
    allocate.add_argument("--date", help="UTC release date in YYYYMMDD format")

    update = subcommands.add_parser("update")
    update.add_argument("--tag", required=True)
    update.add_argument("--aria2-version", required=True)
    update.add_argument("--checksums", required=True, type=Path)
    update.add_argument("--manifest", required=True, type=Path)

    args = parser.parse_args()
    if not re.fullmatch(ARIA2_VERSION, args.aria2_version):
        parser.error(f"Invalid aria2 version: {args.aria2_version}")

    try:
        if args.command == "next-tag":
            print(next_tag(args.aria2_version, args.remote, args.date))
        else:
            update_manifest(args.tag, args.aria2_version, args.checksums, args.manifest)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"git ls-remote failed: {error.stderr.strip()}\n")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
