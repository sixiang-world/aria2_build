#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
upstream=https://github.com/aria2/aria2.git

resolve_commit() {
  local ref=${1:-} exact branch legacy refs commit candidate
  if [[ -z "$ref" ]]; then
    ref="$(cat "$repo_dir/build-aux/aria2.commit")"
  fi
  if [[ "$ref" =~ ^[0-9a-fA-F]{40}$ ]]; then
    printf '%s\n' "$ref" | tr 'A-F' 'a-f'
    return
  fi

  if [[ "$ref" == refs/heads/* || "$ref" == refs/tags/* ]]; then
    git check-ref-format "$ref"
    exact=$ref
    branch=$ref
  else
    git check-ref-format "refs/heads/$ref"
    exact="refs/tags/$ref"
    branch="refs/heads/$ref"
  fi
  legacy=$exact
  if [[ "$ref" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([.-][a-zA-Z0-9.-]+)?$ ]]; then
    legacy="refs/tags/release-${ref#v}"
  fi
  refs="$(git ls-remote "$upstream" "$exact" "$exact^{}" "$branch" "$legacy" "$legacy^{}")"
  for candidate in "$exact^{}" "$exact" "$branch" "$legacy^{}" "$legacy"; do
    commit="$(awk -v ref="$candidate" '$2 == ref {print $1; exit}' <<< "$refs")"
    if [[ -n "$commit" ]]; then
      printf '%s\n' "$commit"
      return
    fi
  done
  printf 'Upstream aria2 ref not found: %s (use a full SHA for commits).\n' "$ref" >&2
  return 1
}

prepare_source() (
  local commit=$1 dest=$2 mode=$3 checkout_dir patch_file
  local -a patches
  if [[ ! "$commit" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Expected a resolved aria2 commit SHA" >&2
    return 2
  fi
  case "$mode" in
    patched|vanilla) ;;
    *) echo "Expected patched or vanilla patch mode" >&2; return 2 ;;
  esac
  if [[ -e "$dest" || -L "$dest" ]]; then
    printf 'aria2 source destination already exists: %s\n' "$dest" >&2
    return 2
  fi

  checkout_dir="$(mktemp -d "${dest}.XXXXXX")"
  trap 'rm -rf -- "$checkout_dir"' EXIT
  git -C "$checkout_dir" init --quiet
  git -C "$checkout_dir" -c advice.detachedHead=false fetch --quiet --depth=1 --no-tags "$upstream" "$commit"
  git -C "$checkout_dir" checkout --quiet --detach FETCH_HEAD
  if [[ "$(git -C "$checkout_dir" rev-parse HEAD)" != "$commit" ]]; then
    echo "aria2 checkout SHA differs from the requested SHA" >&2
    return 1
  fi

  if [[ "$mode" == patched ]]; then
    export LC_ALL=C
    shopt -s nullglob
    patches=("$repo_dir"/patch/*.patch)
    if (( ${#patches[@]} == 0 )); then
      echo "Patched mode requires a non-empty patch queue" >&2
      return 1
    fi
    for patch_file in "${patches[@]}"; do
      printf 'Applying %s\n' "${patch_file##*/}" >&2
      git -C "$checkout_dir" apply --index --whitespace=nowarn "$patch_file"
    done
  fi

  mv -- "$checkout_dir" "$dest"
  trap - EXIT
)

source_version() {
  local version
  version="$(sed -nE 's/^AC_INIT\(\[aria2\],[[:space:]]*\[([^]]+)\].*/\1/p' "$1/configure.ac")"
  if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.+-][a-zA-Z0-9.+-]+)?$ ]]; then
    echo "Unable to determine aria2 package version in $1/configure.ac" >&2
    return 1
  fi
  printf '%s\n' "$version"
}

extract_source() {
  local archive=$1 expected=$2 dest=$3 actual
  if [[ ! "$expected" =~ ^[0-9a-f]{64}$ ]]; then
    echo "Expected a SHA-256 for the aria2 source archive" >&2
    return 2
  fi
  if command -v sha256sum >/dev/null; then
    actual="$(sha256sum "$archive")"
  else
    actual="$(shasum -a 256 "$archive")"
  fi
  if [[ "${actual%% *}" != "$expected" ]]; then
    echo "Prepared aria2 source archive failed the SHA-256 check" >&2
    return 1
  fi
  mkdir -- "$dest"
  tar -xzf "$archive" -C "$dest" --strip-components=1
}

bootstrap_source() (
  cd -- "$1"
  local gettext_version
  # Use one gettext release for both macros and po/Makefile.in.in.
  gettext_version="$(gettext --version | sed -nE '1s/.*[^0-9.]([0-9]+\.[0-9]+)(\.[0-9]+)?.*/\1/p')"
  if [[ ! "$gettext_version" =~ ^[0-9]+\.[0-9]+$ ]]; then
    echo "Unable to determine the installed gettext version" >&2
    return 1
  fi
  sed -E "s/AM_GNU_GETTEXT_VERSION\(\[[0-9.]+\]\)/AM_GNU_GETTEXT_VERSION([$gettext_version])/" \
    configure.ac > configure.ac.tmp
  mv configure.ac.tmp configure.ac
  autopoint --force
  autoreconf -fi
)

case "${1:-}" in
  resolve)
    resolve_commit "${2:-}"
    ;;
  prepare)
    prepare_source "${2:?Missing commit}" "${3:?Missing destination}" "${4:-patched}"
    ;;
  version)
    source_version "${2:?Missing source directory}"
    ;;
  extract)
    extract_source "${2:?Missing source archive}" "${3:?Missing archive checksum}" "${4:?Missing destination}"
    ;;
  bootstrap)
    bootstrap_source "${2:?Missing source directory}"
    ;;
  *)
    echo "Usage: $0 {resolve [ref]|prepare commit directory [patched|vanilla]|version directory|extract archive SHA-256 directory|bootstrap directory}" >&2
    exit 2
    ;;
esac
