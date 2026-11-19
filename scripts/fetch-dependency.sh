#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
name=${1:?Dependency name is required}
cache_dir=${2:?Download directory is required}
lock_file="$repo_dir/build-aux/dependencies.tsv"
record="$(awk -F '\t' -v name="$name" '$1 == name {print}' "$lock_file")"
IFS=$'\t' read -r key version sha url <<< "$record"
if [[ "$key" != "$name" || -z "$version" || ! "$sha" =~ ^[a-f0-9]{64}$ || "$url" != https://* || "$record" == *$'\n'* ]]; then
  printf 'Invalid or missing dependency lock for %s\n' "$name" >&2
  exit 2
fi

filename="${url##*/}"
case "$name" in
  ninja) filename="ninja-$version-linux.zip" ;;
  zlib-ng) filename="zlib-ng-$version.tar.gz" ;;
esac
mkdir -p -- "$cache_dir"
archive="$cache_dir/$filename"
verify() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$sha" "$1" | sha256sum --check --status
  else
    printf '%s  %s\n' "$sha" "$1" | shasum -a 256 --check --status
  fi
}

if [[ ! -f "$archive" ]] || ! verify "$archive"; then
  temp_archive="$(mktemp "$archive.part.XXXXXX")"
  trap 'rm -f -- "$temp_archive"' EXIT
  curl --fail --show-error --silent --location --retry 3 --retry-all-errors \
    --connect-timeout 20 --max-time 300 --proto '=https' --proto-redir '=https' \
    --output "$temp_archive" "$url"
  if ! verify "$temp_archive"; then
    printf 'SHA-256 mismatch for %s %s (%s)\n' "$name" "$version" "$url" >&2
    exit 1
  fi
  mv -f -- "$temp_archive" "$archive"
fi

printf '%s\n' "$archive"
