#!/usr/bin/env bash
# Static cross-building in an abcfy2 toolchain container.
# See build-aux/toolchains.tsv for the CI image digests.
set -euo pipefail

: "${CROSS_HOST:?Set CROSS_HOST or use a supported cross-toolchain container}"
: "${CROSS_ROOT:?Set CROSS_ROOT or use a supported cross-toolchain container}"
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output_dir="${BUILD_OUTPUT_DIR:-$repo_dir}"
download_dir="${DOWNLOADS_DIR:-$repo_dir/downloads}"
PATCH_MODE="${PATCH_MODE:-patched}"
EXCLUDE_PATCHES="${EXCLUDE_PATCHES:-}"
USE_ZLIB_NG="${USE_ZLIB_NG:-1}"
TLS_BACKEND="${TLS_BACKEND:-}"
COMPILER_OPT="${COMPILER_OPT:--O2}"
RUN_TESTS="${RUN_TESTS:-${INSTALL_TEST_RUNNERS:-1}}"
INSTALL_TEST_RUNNERS="${INSTALL_TEST_RUNNERS:-$RUN_TESTS}"
if [[ -n "${ARIA2_SOURCE_ARCHIVE:-}" ]]; then
  ARIA2_SOURCE_ARCHIVE="$(realpath -e "$ARIA2_SOURCE_ARCHIVE")"
fi

normalize_bool() {
  case "${!1}" in
    1|true|TRUE|True|yes|on) printf -v "$1" '%s' 1 ;;
    0|false|FALSE|False|no|off) printf -v "$1" '%s' 0 ;;
    *) printf 'Invalid boolean value for %s: %s\n' "$1" "${!1}" >&2; exit 2 ;;
  esac
}
normalize_bool USE_ZLIB_NG
normalize_bool RUN_TESTS
normalize_bool INSTALL_TEST_RUNNERS
if [[ -z "$TLS_BACKEND" ]]; then
  USE_LIBRESSL="${USE_LIBRESSL:-0}"
  normalize_bool USE_LIBRESSL
  TLS_BACKEND=openssl
  if [[ "$USE_LIBRESSL" == 1 ]]; then
    TLS_BACKEND=libressl
  fi
fi
case "$PATCH_MODE" in
  patched|vanilla) ;;
  *) echo "PATCH_MODE must be patched or vanilla" >&2; exit 2 ;;
esac
case "$TLS_BACKEND" in
  openssl|libressl|wintls) ;;
  *) echo "TLS_BACKEND must be openssl, libressl or wintls" >&2; exit 2 ;;
esac
case "$COMPILER_OPT" in
  -O2|-O3|-Os) ;;
  *) echo "COMPILER_OPT must be -O2, -O3 or -Os" >&2; exit 2 ;;
esac

target_arch="${CROSS_HOST%%-*}"
target_system=Linux
case "$CROSS_HOST" in
  *mingw*) target_system=Windows ;;
esac
if [[ "$target_system" != Windows && "$TLS_BACKEND" == wintls ]]; then
  echo "WinTLS is only available on Windows; using OpenSSL for $CROSS_HOST" >&2
  TLS_BACKEND=openssl
fi

aria2_tls_flags=(--without-appletls --without-gnutls)
libssh2_crypto=openssl
if [[ "$TLS_BACKEND" == wintls ]]; then
  aria2_tls_flags+=(--enable-ssl --with-wintls --without-openssl)
  libssh2_crypto=wincng
else
  aria2_tls_flags+=(--without-wintls --with-openssl)
fi

case "$target_arch" in
  arm* ) openssl_target=linux-armv4 ;;
  aarch64) openssl_target=linux-aarch64 ;;
  mips64*) openssl_target=linux64-mips64 ;;
  mips*) openssl_target=linux-mips32 ;;
  x86_64) openssl_target=linux-x86_64 ;;
  i?86) openssl_target=linux-x86 ;;
  s390x) openssl_target=linux64-s390x ;;
  loongarch64) openssl_target=linux64-loongarch64 ;;
  *) openssl_target=gcc ;;
esac
case "$CROSS_HOST" in
  x86_64*mingw*) openssl_target=mingw64 ;;
  i686*mingw*) openssl_target=mingw ;;
esac

export DEBIAN_FRONTEND=noninteractive
if [[ "${USE_CHINA_MIRROR:-0}" == 1 ]]; then
  if [[ ! -s /etc/ssl/certs/ca-certificates.crt ]]; then
    apt-get -q update
    apt-get -qy install --no-install-recommends ca-certificates
  fi
  # Keep the container's official Ubuntu archive key and apt configuration.
  sed -i -E 's@https?://(archive|security)\.ubuntu\.com/ubuntu/?@https://mirrors.cernet.edu.cn/ubuntu/@g' \
    /etc/apt/sources.list.d/ubuntu.sources
fi
apt-get -q update
build_packages=(
  autoconf automake autopoint binutils ca-certificates curl file g++ gettext git libtool
  make openssl pkgconf python3 unzip xz-utils zip
)
if [[ -n "${CCACHE_DIR:-}" ]]; then
  build_packages+=(ccache)
  export CCACHE_DIR="$(realpath -m -- "$CCACHE_DIR")"
fi
apt-get -qy install --no-install-recommends "${build_packages[@]}"
if [[ "$RUN_TESTS" == 1 && "$INSTALL_TEST_RUNNERS" == 1 ]]; then
  if [[ "$target_system" == Windows ]]; then
    if [[ "$target_arch" == i686 ]]; then
      dpkg --add-architecture i386
      apt-get -q update
      apt-get -qy install --no-install-recommends wine wine32:i386
    else
      apt-get -qy install --no-install-recommends wine wine64
    fi
  elif [[ "$CROSS_HOST" != mips* ]]; then
    # MIPS targets run architecture-only checks in CI and do not need qemu-user.
    apt-get -qy install --no-install-recommends qemu-user
  fi
fi

mkdir -p -- "$output_dir" "$download_dir"
output_dir="$(cd -- "$output_dir" && pwd)"
download_dir="$(cd -- "$download_dir" && pwd)"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
prefix="$work_dir/prefix"
mkdir -p "$prefix/lib" "$prefix/include"

export PATH="$CROSS_ROOT/bin:$work_dir/tools/bin:$PATH"
export CC="$CROSS_HOST-cc" CXX="$CROSS_HOST-c++" CPP="$CROSS_HOST-cpp"
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig:$prefix/lib64/pkgconfig"
unset PKG_CONFIG_PATH
export CPPFLAGS="-I$prefix/include"
export LDFLAGS="-L$prefix/lib -L$prefix/lib64"

# Security hardening flags for aria2 compilation.
aria2_hardening_cflags="-fstack-protector-strong -Wformat -Werror=format-security"
aria2_hardening_ldflags="-static"
if [[ "$target_system" == Linux ]]; then
  aria2_hardening_ldflags="$aria2_hardening_ldflags -Wl,-z,relro,-z,now -Wl,-z,noexecstack"
fi

# Embed a Windows longPathAware application manifest without modifying upstream sources.
if [[ "$target_system" == Windows && -f "$repo_dir/build-aux/aria2c.rc" ]]; then
  "$CROSS_HOST-windres" --include-dir="$repo_dir/build-aux" -O coff \
    -i "$repo_dir/build-aux/aria2c.rc" -o "$work_dir/aria2c_manifest.o"
  aria2_hardening_ldflags="$aria2_hardening_ldflags -Wl,$work_dir/aria2c_manifest.o"
fi

jobs="${BUILD_JOBS:-$(nproc)}"
build_arch="$(gcc -dumpmachine)"
build_info="$output_dir/build_info.md"
notices="$work_dir/THIRD-PARTY-NOTICES.txt"
printf '%s\n' 'Direct third-party libraries linked into this aria2 build' > "$notices"
{
  printf '## Aria2 build for %s\n\n' "$CROSS_HOST"
  printf -- '- Toolchain image: %s\n' "${TOOLCHAIN_IMAGE:-not specified}"
  printf -- '- Compiler: %s\n' "$("$CXX" --version | sed -n '1p')"
  printf -- '- Patch mode: %s\n' "$PATCH_MODE"
  printf -- '- Excluded patches: %s\n' "${EXCLUDE_PATCHES:-none}"
  printf -- '- TLS backend: %s\n' "$TLS_BACKEND"
  printf -- '- Tests enabled: %s\n' "$RUN_TESTS"
  printf -- '- Aria2 CFLAGS/CXXFLAGS: %s %s\n' "$aria2_hardening_cflags" "$COMPILER_OPT"
  printf -- '- Aria2 LDFLAGS extra: %s\n' "$aria2_hardening_ldflags"
} > "$build_info"

archive_for() {
  local dependency=$1 archive
  archive="$("$repo_dir/scripts/fetch-dependency.sh" "$dependency" "$download_dir")" || return
  awk -F '\t' -v name="$dependency" '$1 == name {printf "- %s %s (SHA-256 %s), source: %s\n", $1, $2, $3, $4}' \
    "$repo_dir/build-aux/dependencies.tsv" >> "$build_info"
  printf '%s\n' "$archive"
}

unpack() {
  local dependency=$1 archive
  archive="$(archive_for "$dependency")"
  mkdir -- "$work_dir/$dependency"
  tar -xaf "$archive" --strip-components=1 -C "$work_dir/$dependency"
  cd -- "$work_dir/$dependency"
}

build_autotools() {
  ./configure --host="$CROSS_HOST" --prefix="$prefix" --libdir="$prefix/lib" \
    --enable-static --disable-shared "$@"
  make -j"$jobs"
  make install
}

append_license() {
  local dependency=$1 license=$2
  {
    printf '\n===== %s / %s =====\n\n' "$dependency" "$license"
    cat "$work_dir/$dependency/$license"
    printf '\n'
  } >> "$notices"
}

if [[ "$USE_ZLIB_NG" == 1 ]]; then
  mkdir -p "$work_dir/tools/bin"
  cmake_archive="$(archive_for cmake)"
  ninja_archive="$(archive_for ninja)"
  tar -xaf "$cmake_archive" --strip-components=1 -C "$work_dir/tools"
  unzip -q "$ninja_archive" -d "$work_dir/tools/bin"
  unpack zlib-ng
  append_license zlib-ng LICENSE.md
  cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF -DZLIB_COMPAT=ON -DBUILD_TESTING=OFF \
    -DCMAKE_SYSTEM_NAME="$target_system" -DCMAKE_SYSTEM_PROCESSOR="$target_arch" \
    -DCMAKE_INSTALL_PREFIX="$prefix" -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_C_COMPILER="$CC"
  cmake --build build --parallel "$jobs"
  cmake --install build
  # zlib-ng emits an unset sharedlibdir in MinGW static .pc files.
  sed -i "s@^sharedlibdir=.*@sharedlibdir=\${libdir}@" "$prefix/lib/pkgconfig/zlib.pc"
else
  unpack zlib
  append_license zlib LICENSE
  if [[ "$target_system" == Windows ]]; then
    make -f win32/Makefile.gcc -j"$jobs" BINARY_PATH="$prefix/bin" \
      INCLUDE_PATH="$prefix/include" LIBRARY_PATH="$prefix/lib" \
      SHARED_MODE=0 PREFIX="$CROSS_HOST-" install
  else
    CHOST="$CROSS_HOST" ./configure --prefix="$prefix" --static
    make -j"$jobs"
    make install
  fi
fi

if [[ "$TLS_BACKEND" == libressl ]]; then
  unpack libressl
  append_license libressl COPYING
  build_autotools --disable-tests --with-openssldir=/etc/ssl
elif [[ "$TLS_BACKEND" == openssl ]]; then
  unpack openssl
  append_license openssl LICENSE.txt
  openssl_libs=()
  if [[ "$CROSS_HOST" == i686-unknown-linux-musl ]]; then
    # The i686 Clang target emits generic atomics for OpenSSL's pthread code.
    # Configure records this runtime library in libcrypto.pc for static consumers.
    openssl_libs+=(-latomic)
    printf '%s\n' '- libatomic: from the locked i686 toolchain' >> "$build_info"
  fi
  # OpenSSL's cross-compile-prefix prepends the triplet to the native names.
  # aria2 loads the legacy provider on startup, so embed it in libcrypto.
  CC=cc CXX=c++ CPP=cpp ./Configure --cross-compile-prefix="$CROSS_HOST-" \
    --prefix="$prefix" --libdir=lib --openssldir=/etc/ssl no-shared no-module no-tests no-apps \
    "$openssl_target" "${openssl_libs[@]}"
  make -j"$jobs" build_sw
  make install_sw
fi

# musl and glibc provide iconv themselves. MinGW requires libiconv for XML.
if [[ "$target_system" == Windows ]]; then
  unpack libiconv
  append_license libiconv COPYING.LIB
  build_autotools
fi
unpack libxml2
append_license libxml2 Copyright
build_autotools --without-icu --with-zlib

unpack sqlite
printf '\n%s\n%s\n' '===== SQLite =====' \
  'SQLite is dedicated to the public domain. See https://www.sqlite.org/copyright.html.' >> "$notices"
sqlite_flags=()
if [[ "$target_system" == Windows ]]; then
  sqlite_flags+=(--disable-load-extension)
fi
build_autotools --build="$build_arch" "${sqlite_flags[@]}"
if [[ -f "$prefix/lib/libsqlite3.lib" && ! -e "$prefix/lib/libsqlite3.a" ]]; then
  ln -s libsqlite3.lib "$prefix/lib/libsqlite3.a"
fi

unpack c-ares
append_license c-ares LICENSE.md
build_autotools --disable-tests
unpack libssh2
append_license libssh2 COPYING
for license in "$work_dir/libssh2/LICENSES/"*.txt; do
  append_license libssh2 "LICENSES/${license##*/}"
done
autoreconf -fi
build_autotools --disable-examples-build --with-crypto="$libssh2_crypto"

# Bundle verified Mozilla CA certificates for OpenSSL-compatible Windows builds.
if [[ "$target_system" == Windows && "$TLS_BACKEND" != wintls ]]; then
  cacert_file="$(archive_for cacert)"
  install -m 644 "$cacert_file" "$output_dir/cacert.pem"
  printf '\n%s\n%s\n' '===== Mozilla CA Certificate Bundle (curl.se) =====' \
    'Derived from Mozilla NSS certdata.txt under MPL-2.0. See https://curl.se/docs/caextract.html.' >> "$notices"
fi

source_dir="$work_dir/aria2"
if [[ -n "${ARIA2_SOURCE_ARCHIVE:-}" ]]; then
  : "${ARIA2_SOURCE_SHA256:?Set the SHA-256 of the prepared source archive}"
  : "${ARIA2_COMMIT:?Set the commit of the prepared source archive}"
  "$repo_dir/scripts/aria2-source.sh" extract "$ARIA2_SOURCE_ARCHIVE" "$ARIA2_SOURCE_SHA256" "$source_dir"
else
  ARIA2_COMMIT="$("$repo_dir/scripts/aria2-source.sh" resolve "${ARIA2_REF:-${ARIA2_VER:-}}")"
  EXCLUDE_PATCHES="$EXCLUDE_PATCHES" "$repo_dir/scripts/aria2-source.sh" \
    prepare "$ARIA2_COMMIT" "$source_dir" "$PATCH_MODE"
fi
version="$("$repo_dir/scripts/aria2-source.sh" version "$source_dir")"
"$repo_dir/scripts/aria2-source.sh" bootstrap "$source_dir"
cd -- "$source_dir"
aria2_cppflags="$CPPFLAGS"
if [[ "$TLS_BACKEND" == wintls ]]; then
  # Upstream's Automake conditional does not reach FeatureConfig.cc.
  aria2_cppflags+=" -DHAVE_WINTLS=1"
fi
aria2_cc="$CC"
aria2_cxx="$CXX"
if [[ -n "${CCACHE_DIR:-}" ]]; then
  # Cross-builds unpack aria2 into a different temporary path on every run.
  export CCACHE_BASEDIR="$work_dir"
  ccache --zero-stats
  aria2_cc="ccache $CC"
  aria2_cxx="ccache $CXX"
fi
CC="$aria2_cc" CXX="$aria2_cxx" \
CFLAGS="${CFLAGS:+$CFLAGS }$aria2_hardening_cflags" \
CXXFLAGS="${CXXFLAGS:+$CXXFLAGS }$aria2_hardening_cflags" \
LDFLAGS="$LDFLAGS $aria2_hardening_ldflags" \
COMPILER_OPT="$COMPILER_OPT" "$repo_dir/scripts/aria2-source.sh" configure "$source_dir" \
  --host="$CROSS_HOST" --prefix="$prefix" \
  --enable-static --disable-shared --enable-silent-rules "${aria2_tls_flags[@]}" \
  --with-libz --with-libxml2 --with-sqlite3 --with-libcares --with-libssh2 \
  "CPPFLAGS=$aria2_cppflags" ARIA2_STATIC=yes
make -j"$jobs"
if [[ -n "${CCACHE_DIR:-}" ]]; then
  ccache --show-stats
fi

binary=aria2c
if [[ "$target_system" == Windows ]]; then
  binary=aria2c.exe
fi
"$CROSS_HOST-strip" --strip-unneeded "src/$binary"
install -m 755 "src/$binary" "$output_dir/$binary"
install -m 644 COPYING LICENSE.OpenSSL "$notices" "$output_dir"
{
  printf -- '- Aria2 version: %s\n' "$version"
  printf -- '- Aria2 commit: %s\n' "$ARIA2_COMMIT"
  if [[ -n "${ARIA2_SOURCE_SHA256:-}" ]]; then
    printf -- '- Aria2 source archive SHA-256: %s\n' "$ARIA2_SOURCE_SHA256"
  fi
  printf -- '- Binary SHA-256: %s\n' "$(sha256sum "$output_dir/$binary" | cut -d' ' -f1)"
  file "$output_dir/$binary"
} >> "$build_info"
file "$output_dir/$binary"

if [[ "$RUN_TESTS" == 1 ]]; then
  test_options=(--target "$CROSS_HOST" --patch-mode "$PATCH_MODE" --exclude-patches "$EXCLUDE_PATCHES")
  if [[ "$target_system" == Windows ]]; then
    export WINEPREFIX="$work_dir/wine" WINEDEBUG=-all
    test_options+=(--runner wine)
  else
    test_options+=(--require-static)
    case "$CROSS_HOST" in
      aarch64*) test_options+=(--runner qemu-aarch64) ;;
      arm*) test_options+=(--runner qemu-arm) ;;
      mips*) test_options+=(--architecture-only) ;;
      loongarch64*)
        if command -v qemu-loongarch64 >/dev/null; then
          test_options+=(--runner qemu-loongarch64)
        else
          test_options+=(--architecture-only)
        fi
        ;;
    esac
  fi
  TLS_BACKEND="$TLS_BACKEND" "$repo_dir/scripts/test.sh" "$output_dir/$binary" "${test_options[@]}"
else
  echo "Skipping tests (RUN_TESTS=false)"
fi
