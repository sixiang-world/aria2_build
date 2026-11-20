#!/usr/bin/env python3
"""Select a stable or master candidate and publish a separately verified build."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


UPSTREAM = "https://github.com/aria2/aria2.git"
COMMIT_LOCK = Path("build-aux/aria2.commit")
TAG_LOCK = Path("build-aux/aria2.release")
SCOOP_MANIFEST = Path("bucket/aria2.json")
SCOOP_SCRIPT = Path(__file__).resolve().with_name("update-scoop-manifest.py")
STABLE_TAG = re.compile(r"release-([0-9]+)\.([0-9]+)\.([0-9]+)")
SHA = re.compile(r"[0-9a-f]{40}")


def command(*args, input_text=None, check=True):
    try:
        result = subprocess.run(args, input=input_text, text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{args[0]} {args[1]} timed out") from error
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]}: {result.stderr.strip()}")
    return result


def refs(remote, *patterns):
    return {
        ref: sha
        for sha, ref in (line.split() for line in command("git", "ls-remote", remote, *patterns).stdout.splitlines())
    }


def discover():
    locked_commit = COMMIT_LOCK.read_text().strip()
    locked_tag = TAG_LOCK.read_text().strip()
    baseline = STABLE_TAG.fullmatch(locked_tag)
    if not SHA.fullmatch(locked_commit) or not baseline:
        raise RuntimeError("Invalid aria2 upstream lock files")

    baseline_version = tuple(map(int, baseline.groups()))
    master_ref = "refs/heads/master"
    upstream_refs = refs(UPSTREAM, master_ref, "refs/tags/release-*")
    master = upstream_refs.get(master_ref, "")
    stable_tags = {}
    for ref, commit in upstream_refs.items():
        tag = ref.removeprefix("refs/tags/")
        version = STABLE_TAG.fullmatch(tag)
        if version:
            stable_tags[tuple(map(int, version.groups()))] = (tag, upstream_refs.get(f"{ref}^{{}}", commit))
    if not SHA.fullmatch(master) or baseline_version not in stable_tags:
        raise RuntimeError("Upstream master or the baseline stable tag is missing")

    latest_version = max(stable_tags)
    if latest_version > baseline_version:
        tag, commit = stable_tags[latest_version]
    elif master != locked_commit:
        tag, commit = "", master
    else:
        print("Upstream master and stable tag are unchanged", file=sys.stderr)
        return
    if not SHA.fullmatch(commit):
        raise RuntimeError(f"Upstream candidate has an invalid SHA: {commit}")
    print(f"Selected {tag or 'master'} at {commit}", file=sys.stderr)
    print(f"commit={commit}\ntag={tag}")


def release_api(suffix="", *, method="GET", payload=None, missing_ok=False):
    endpoint = f"repos/{os.environ['GITHUB_REPOSITORY']}/releases{suffix}"
    args = ("gh", "api", "--method", method, endpoint)
    if payload is not None:
        args += ("--input", "-")
    result = command(*args, input_text=json.dumps(payload) if payload is not None else None, check=False)
    if result.returncode:
        if missing_ok and re.search(r"\(HTTP 404\)", result.stderr):
            return None
        raise RuntimeError(f"{method} {endpoint}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout) if result.stdout else None
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{method} {endpoint} returned invalid JSON") from error


def push_refs(previous, updates):
    # A single transaction covers the default branch and release tag. Explicit
    # leases protect against concurrent changes, including creation of the tag.
    leases = tuple(f"--force-with-lease={ref}:{previous[ref]}" for ref in updates)
    refspecs = tuple(f"{commit}:{ref}" for ref, commit in updates.items())
    command("git", "push", "--atomic", *leases, "origin", *refspecs)


def lock_commit(candidate, upstream_tag, release_tag, aria2_version):
    command(
        sys.executable, str(SCOOP_SCRIPT), "update", "--tag", release_tag,
        "--aria2-version", aria2_version, "--checksums", "release/SHA256SUMS",
        "--manifest", str(SCOOP_MANIFEST),
    )
    paths = [str(COMMIT_LOCK), str(SCOOP_MANIFEST)]
    COMMIT_LOCK.write_text(f"{candidate}\n")
    if upstream_tag:
        TAG_LOCK.write_text(f"{upstream_tag}\n")
        paths.append(str(TAG_LOCK))
    command("git", "add", "--", *paths)
    command(
        "git", "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", f"chore: sync aria2 {upstream_tag or candidate}",
    )
    return command("git", "rev-parse", "HEAD").stdout.strip()


def publish():
    candidate = os.environ["CANDIDATE"]
    upstream_tag = os.environ["UPSTREAM_TAG"]
    aria2_version = os.environ["ARIA2_VERSION"]
    if not SHA.fullmatch(candidate) or (upstream_tag and not STABLE_TAG.fullmatch(upstream_tag)):
        raise RuntimeError("Invalid tested upstream candidate")

    branch = os.environ["GITHUB_REF"]
    base = os.environ["GITHUB_SHA"]
    tag = command(sys.executable, str(SCOOP_SCRIPT), "next-tag", "--aria2-version", aria2_version).stdout.strip()
    tag_ref = f"refs/tags/{tag}"
    attempt = f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    staging_tag = f"aria2-sync-draft-{attempt}"
    before = refs("origin", branch, tag_ref)
    if before.get(branch) != base or command("git", "rev-parse", "HEAD").stdout.strip() != base:
        raise RuntimeError("The default branch advanced while the candidate was being tested")
    if tag_ref in before or release_api(f"/tags/{tag}", missing_ok=True) is not None:
        raise RuntimeError(f"The downstream tag or release {tag} already exists")

    assets = sorted(path for path in Path("release").iterdir() if path.is_file())
    expected_assets = {path.name: path.stat().st_size for path in assets}
    body = Path("release/build_info.md").read_text()
    new_commit = lock_commit(candidate, upstream_tag, tag, aria2_version)
    old_refs = {branch: base, tag_ref: ""}
    new_refs = {branch: new_commit, tag_ref: new_commit}
    draft_endpoint = None
    push_attempted = False
    promotion_attempted = False
    try:
        # Upload everything to a run-scoped draft before mutating public refs.
        draft = release_api(method="POST", payload={
            "tag_name": staging_tag,
            "target_commitish": base,
            "name": f"Aria2 {tag.removeprefix('v')}",
            "body": body,
            "prerelease": False,
            "draft": True,
        })
        draft_endpoint = f"/{draft['id']}"
        command("gh", "release", "upload", "--repo", os.environ["GITHUB_REPOSITORY"], staging_tag,
                *(str(path) for path in assets))
        draft = release_api(draft_endpoint)
        uploaded_assets = {asset["name"]: asset["size"] for asset in draft["assets"] if asset["state"] == "uploaded"}
        if not draft["draft"] or draft["tag_name"] != staging_tag or uploaded_assets != expected_assets:
            raise RuntimeError("The staged release assets do not match the tested manifest")

        push_attempted = True
        push_refs(old_refs, new_refs)
        promotion_attempted = True
        published = release_api(draft_endpoint, method="PATCH", payload={
            "tag_name": tag,
            "target_commitish": new_commit,
            "draft": False,
            "make_latest": "true",
        })
        if not published or published.get("draft") is not False or published.get("tag_name") != tag:
            raise RuntimeError(f"Release API did not confirm promotion of {tag}")
    except (RuntimeError, OSError) as error:
        published = None
        if promotion_attempted:
            # A lost response may hide a successful promotion. Read the exact
            # release ID before attempting to restore the branch and tag.
            try:
                published = release_api(draft_endpoint)
            except (RuntimeError, OSError) as verification_error:
                raise RuntimeError(
                    f"Promotion status is unknown for {draft_endpoint}; inspect {tag} and the "
                    f"default branch before retrying. Promotion: {error}. Status: {verification_error}"
                ) from error
        if not published or published["draft"] or published["tag_name"] != tag:
            restore_release(old_refs, new_refs, push_attempted, draft_endpoint)
            raise
        print(f"Confirmed release {tag} after an interrupted API response")

    print(f"Published {tag} for upstream {candidate} from {new_commit}")


def restore_release(old_refs, new_refs, push_attempted, draft_endpoint):
    try:
        if push_attempted:
            current = refs("origin", *new_refs)
            owned = {ref: old_refs[ref] for ref, commit in new_refs.items() if current.get(ref) == commit}
            if owned:
                push_refs(new_refs, owned)
                current.update(owned)
            if any(current.get(ref, "") != commit for ref, commit in old_refs.items()):
                raise RuntimeError("The default branch or release tag advanced concurrently; leases forbid further rollback")
    except (RuntimeError, OSError) as error:
        print(f"::error::Could not restore upstream sync refs: {error}", file=sys.stderr)
    try:
        if draft_endpoint:
            draft = release_api(draft_endpoint)
            if draft["draft"]:
                release_api(draft_endpoint, method="DELETE")
    except (RuntimeError, OSError) as error:
        print(f"::error::Could not remove the upstream sync draft: {error}", file=sys.stderr)


if __name__ == "__main__":
    try:
        {"discover": discover, "publish": publish}[sys.argv[1]]()
    except (RuntimeError, OSError) as error:
        sys.exit(str(error))
