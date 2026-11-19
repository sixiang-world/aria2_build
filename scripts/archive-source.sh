#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "Usage: $0 SOURCE_DIR ARCHIVE UPSTREAM_COMMIT patched|vanilla" >&2
    exit 2
fi

source_dir=$1
archive=$2
upstream_commit=$3
patch_mode=$4
build_repo=$(cd -- "$(dirname -- "$0")/.." && pwd)

if [[ $upstream_commit != "$(git -C "$source_dir" rev-parse HEAD)" ]]; then
    echo "Source HEAD does not match the selected upstream commit" >&2
    exit 1
fi
if ! git -C "$source_dir" diff --quiet --; then
    echo "Source contains unstaged changes" >&2
    exit 1
fi
case "$patch_mode" in
    patched)
        if git -C "$source_dir" diff --cached --quiet --; then
            echo "Patched source must have its changes staged" >&2
            exit 1
        fi
        ;;
    vanilla)
        if ! git -C "$source_dir" diff --cached --quiet --; then
            echo "Vanilla source contains staged changes" >&2
            exit 1
        fi
        ;;
    *)
        echo "Unknown patch mode: $patch_mode" >&2
        exit 2
        ;;
esac

source_tree=$(git -C "$source_dir" write-tree)
build_commit=$(git -C "$build_repo" rev-parse HEAD)
timestamp=$(git -C "$source_dir" show -s --format=%ct HEAD)
scratch=$(mktemp -d)
temp_archive=
trap 'rm -rf -- "$scratch"; if [[ -n $temp_archive ]]; then rm -f -- "$temp_archive"; fi' EXIT

mkdir -p -- "$scratch/aria2-source"
git -C "$source_dir" archive "$source_tree" | tar -x -C "$scratch/aria2-source"
recipes=(build.sh build-aux scripts patch README.md docs/distribution.md
    .github/workflows/full.yml .github/workflows/lite.yml .github/workflows/prepare-source.yml)
git -C "$build_repo" archive --prefix=aria2-source/build-recipes/ \
    "$build_commit" "${recipes[@]}" | tar -x -C "$scratch"
printf '%s\n' \
    "upstream_commit=$upstream_commit" \
    "source_tree=$source_tree" \
    "build_repo_commit=$build_commit" \
    "patch_mode=$patch_mode" > "$scratch/aria2-source/SOURCE-PROVENANCE.txt"

mkdir -p -- "$(dirname -- "$archive")"
temp_archive=$(mktemp "${archive}.XXXXXX")
tar --sort=name --mtime="@$timestamp" --owner=0 --group=0 --numeric-owner \
    -C "$scratch" -cf - aria2-source | gzip -n > "$temp_archive"
mv -f -- "$temp_archive" "$archive"
temp_archive=
