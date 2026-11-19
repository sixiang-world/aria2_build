#!/usr/bin/env python3
"""Check pinned versions in build-aux/dependencies.tsv against upstream releases."""

import json
import os
from pathlib import Path
import re
import sys
import urllib.request


USER_AGENT = "aria2_build-dependency-checker/1.0"


def fetch_text(url):
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def github_latest_tag(repo, prefix=""):
    data = json.loads(fetch_text(f"https://api.github.com/repos/{repo}/releases/latest"))
    tag = data["tag_name"]
    return tag[len(prefix):] if prefix and tag.startswith(prefix) else tag


def check_latest(name, pinned):
    try:
        if name == "cmake":
            return github_latest_tag("Kitware/CMake", "v")
        if name == "ninja":
            return github_latest_tag("ninja-build/ninja", "v")
        if name == "zlib-ng":
            return github_latest_tag("zlib-ng/zlib-ng")
        if name == "zlib":
            return github_latest_tag("madler/zlib", "v")
        if name == "openssl":
            # Track the pinned 3.5 LTS series automatically.
            releases = json.loads(
                fetch_text("https://api.github.com/repos/openssl/openssl/releases?per_page=30")
            )
            series = ".".join(pinned.split(".")[:2]) + "."
            for rel in releases:
                tag = rel.get("tag_name", "")
                if tag.startswith(f"openssl-{series}") and not rel.get("prerelease"):
                    return tag[len("openssl-"):]
            return "unknown"
        if name == "c-ares":
            return github_latest_tag("c-ares/c-ares", "v")
        if name == "libssh2":
            data = json.loads(fetch_text("https://api.github.com/repos/libssh2/libssh2/commits/master"))
            return f"master-{data['sha'][:7]}"
        if name == "libressl":
            html = fetch_text("https://cdn.openbsd.org/pub/OpenBSD/LibreSSL/")
            vers = sorted(
                set(re.findall(r"libressl-(\d+\.\d+\.\d+)\.tar\.gz", html)),
                key=lambda v: tuple(map(int, v.split("."))),
            )
            return vers[-1] if vers else "unknown"
        if name == "libiconv":
            html = fetch_text("https://ftp.gnu.org/gnu/libiconv/")
            vers = sorted(
                set(re.findall(r"libiconv-(\d+\.\d+(?:\.\d+)?)\.tar\.gz", html)),
                key=lambda v: tuple(map(int, v.split("."))),
            )
            return vers[-1] if vers else "unknown"
        if name == "sqlite":
            html = fetch_text("https://www.sqlite.org/download.html")
            m = re.search(r"sqlite-autoconf-(\d)(\d\d)(\d\d)\d\d\.tar\.gz", html)
            return f"{int(m[1])}.{int(m[2])}.{int(m[3])}" if m else "unknown"
        if name == "cacert":
            html = fetch_text("https://curl.se/docs/caextract.html")
            m = re.search(r"cacert-(\d{4}-\d{2}-\d{2})\.pem", html)
            return m[1] if m else "unknown"
        if name == "libxml2":
            tags = json.loads(
                fetch_text("https://gitlab.gnome.org/api/v4/projects/GNOME%2Flibxml2/repository/tags?per_page=10")
            )
            for t in tags:
                m = re.fullmatch(r"v(\d+\.\d+\.\d+)", t.get("name", ""))
                if m:
                    return m[1]
            return "unknown"
    except Exception as exc:
        return f"error: {exc}"
    return "manual"


def main():
    lock_file = Path(__file__).resolve().parents[1] / "build-aux/dependencies.tsv"
    rows = []
    outdated = 0
    for line in lock_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, version, _sha, _url = stripped.split("\t", 3)
        latest = check_latest(name, version)
        if latest == version or (name == "libssh2" and latest.endswith(version.split("-")[-1])):
            status = "up-to-date"
        elif latest.startswith("error:") or latest in {"unknown", "manual"}:
            status = "check-failed"
        else:
            status = "update-available"
            outdated += 1
        rows.append((name, version, latest, status))

    lines = [
        "## Dependency Version Audit",
        "",
        "| Dependency | Pinned | Upstream Latest | Status |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for name, version, latest, status in rows:
        lines.append(f"| `{name}` | `{version}` | `{latest}` | `{status}` |")
    report = "\n".join(lines) + "\n"
    print(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(report)
    if "--fail-on-outdated" in sys.argv and outdated:
        sys.exit(1)


if __name__ == "__main__":
    main()
