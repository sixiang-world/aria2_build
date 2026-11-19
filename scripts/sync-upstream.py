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
    # leases also protect against concurrent changes to the rolling release tag.
    leases = tuple(f"--force-with-lease={ref}:{previous[ref]}" for ref in updates)
    refspecs = tuple(f"{commit}:{ref}" for ref, commit in updates.items())
    command("git", "push", "--atomic", *leases, "origin", *refspecs)


def lock_commit(candidate, upstream_tag):
    COMMIT_LOCK.write_text(f"{candidate}\n")
    if upstream_tag:
        TAG_LOCK.write_text(f"{upstream_tag}\n")
    command("git", "add", "--", str(COMMIT_LOCK), str(TAG_LOCK))
    command(
        "git", "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", f"chore: sync aria2 {upstream_tag or candidate}",
    )
    return command("git", "rev-parse", "HEAD").stdout.strip()


def publish():
    candidate = os.environ["CANDIDATE"]
    upstream_tag = os.environ["UPSTREAM_TAG"]
    if not SHA.fullmatch(candidate) or (upstream_tag and not STABLE_TAG.fullmatch(upstream_tag)):
        raise RuntimeError("Invalid tested upstream candidate")

    branch = os.environ["GITHUB_REF"]
    base = os.environ["GITHUB_SHA"]
    tag = upstream_tag or "continuous"
    tag_ref = f"refs/tags/{tag}"
    attempt = f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    staging_tag = f"aria2-sync-draft-{attempt}"
    backup_tag = f"aria2-sync-previous-{attempt}"
    backup_ref = f"refs/tags/{backup_tag}"
    before = refs("origin", branch, tag_ref, backup_ref)
    if before.get(branch) != base or command("git", "rev-parse", "HEAD").stdout.strip() != base:
        raise RuntimeError("The default branch advanced while the candidate was being tested")
    if backup_ref in before:
        raise RuntimeError(f"The backup tag {backup_tag} already exists")
    original_tag_sha = before.get(tag_ref, "")
    previous = release_api(f"/tags/{tag}", missing_ok=True)
    if upstream_tag and (original_tag_sha or previous):
        raise RuntimeError(f"The downstream stable tag or release {tag} already exists")
    if previous and (previous.get("immutable") or not previous["prerelease"] or not original_tag_sha):
        raise RuntimeError(f"The existing {tag} release cannot be replaced safely")
    if original_tag_sha:
        command("git", "fetch", "--no-tags", "origin", tag_ref)
        if command("git", "rev-parse", "FETCH_HEAD").stdout.strip() != original_tag_sha:
            raise RuntimeError(f"The downstream {tag} tag changed during release preparation")

    assets = sorted(path for path in Path("release").iterdir() if path.is_file())
    expected_assets = {path.name: path.stat().st_size for path in assets}
    body = Path("release/build_info.md").read_text()
    new_commit = lock_commit(candidate, upstream_tag)
    old_refs = {branch: base, tag_ref: original_tag_sha}
    new_refs = {branch: new_commit, tag_ref: new_commit}
    draft_endpoint = None
    previous_endpoint = f"/{previous['id']}" if previous else None
    backup_attempted = False
    push_attempted = False
    promotion_attempted = False
    try:
        # Upload everything to a run-scoped draft before mutating public refs.
        draft = release_api(method="POST", payload={
            "tag_name": staging_tag,
            "target_commitish": base,
            "name": f"Aria2 {tag.removeprefix('release-')}" if upstream_tag else "Continuous build",
            "body": body,
            "prerelease": not upstream_tag,
            "draft": True,
        })
        draft_endpoint = f"/{draft['id']}"
        command("gh", "release", "upload", "--repo", os.environ["GITHUB_REPOSITORY"], staging_tag,
                *(str(path) for path in assets))
        draft = release_api(draft_endpoint)
        uploaded_assets = {asset["name"]: asset["size"] for asset in draft["assets"] if asset["state"] == "uploaded"}
        if not draft["draft"] or draft["tag_name"] != staging_tag or uploaded_assets != expected_assets:
            raise RuntimeError("The staged release assets do not match the tested manifest")

        if previous_endpoint:
            # Keep the existing release and assets available for compensation
            # while freeing the rolling tag for promotion.
            backup_attempted = True
            push_refs({backup_ref: ""}, {backup_ref: original_tag_sha})
            parked = release_api(previous_endpoint, method="PATCH", payload={"tag_name": backup_tag})
            if parked["tag_name"] != backup_tag:
                raise RuntimeError(f"Could not move the previous {tag} release to {backup_tag}")

        push_attempted = True
        push_refs(old_refs, new_refs)
        promotion_attempted = True
        published = release_api(draft_endpoint, method="PATCH", payload={
            "tag_name": tag,
            "target_commitish": new_commit,
            "draft": False,
            "make_latest": "true" if upstream_tag else "false",
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
            restore_release(old_refs, new_refs, push_attempted, previous_endpoint, tag,
                            backup_attempted, backup_ref, backup_tag, draft_endpoint)
            raise
        print(f"Confirmed release {tag} after an interrupted API response")

    print(f"Published {tag} for upstream {candidate} from {new_commit}")
    if previous_endpoint:
        try:
            if release_api(previous_endpoint)["tag_name"] != backup_tag:
                raise RuntimeError("The previous release was moved concurrently")
            release_api(previous_endpoint, method="DELETE")
            push_refs({backup_ref: original_tag_sha}, {backup_ref: ""})
        except (RuntimeError, OSError) as error:
            print(f"::warning::Could not remove superseded {backup_tag}: {error}")


def restore_release(old_refs, new_refs, push_attempted, previous_endpoint, tag,
                    backup_attempted, backup_ref, backup_tag, draft_endpoint):
    try:
        if push_attempted:
            current = refs("origin", *new_refs)
            owned = {ref: old_refs[ref] for ref, commit in new_refs.items() if current.get(ref) == commit}
            if owned:
                push_refs(new_refs, owned)
                current.update(owned)
            if any(current.get(ref, "") != commit for ref, commit in old_refs.items()):
                raise RuntimeError("The default branch or release tag advanced concurrently; leases forbid further rollback")
        if backup_attempted:
            previous = release_api(previous_endpoint)
            if previous["tag_name"] == backup_tag:
                release_api(previous_endpoint, method="PATCH", payload={"tag_name": tag})
            elif previous["tag_name"] != tag:
                raise RuntimeError("The previous release was moved concurrently")
            backup_sha = refs("origin", backup_ref).get(backup_ref)
            if backup_sha == old_refs[f"refs/tags/{tag}"]:
                push_refs({backup_ref: backup_sha}, {backup_ref: ""})
            elif backup_sha:
                raise RuntimeError("The previous release tag advanced concurrently; lease forbids cleanup")
        if draft_endpoint:
            draft = release_api(draft_endpoint)
            if draft["draft"]:
                release_api(draft_endpoint, method="DELETE")
    except (RuntimeError, OSError) as error:
        print(f"::error::Could not restore upstream sync refs or releases: {error}", file=sys.stderr)


if __name__ == "__main__":
    try:
        {"discover": discover, "publish": publish}[sys.argv[1]]()
    except (RuntimeError, OSError) as error:
        sys.exit(str(error))
