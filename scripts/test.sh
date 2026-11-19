#!/usr/bin/env bash
# Validate an aria2 build with optional QEMU or Wine execution.
set -uo pipefail

usage() {
  cat <<'USAGE'
Usage: test.sh BINARY [--runner RUNNER] [--target PLATFORM] [--lite]
                      [--patch-mode patched|vanilla] [--require-static]
                      [--architecture-only]

--require-static     Require an ELF binary without a dynamic loader or shared libraries
--architecture-only  Check the file without running it (requires --target)
USAGE
}

BINARY=""
RUNNER=""
TARGET=""
LITE_MODE=0
PATCH_MODE=patched
REQUIRE_STATIC=0
ARCHITECTURE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runner|--target|--patch-mode)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        usage >&2
        exit 2
      fi
      case "$1" in
        --runner) RUNNER="$2" ;;
        --target) TARGET="$2" ;;
        --patch-mode) PATCH_MODE="$2" ;;
      esac
      shift 2 ;;
    --lite) LITE_MODE=1; shift ;;
    --require-static) REQUIRE_STATIC=1; shift ;;
    --architecture-only) ARCHITECTURE_ONLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --*) usage >&2; exit 2 ;;
    *)
      if [[ -n "$BINARY" ]]; then
        usage >&2
        exit 2
      fi
      BINARY="$1"
      shift ;;
  esac
done

if [[ ! -f "$BINARY" ]]; then
  echo "❌ 未找到二进制文件 '$BINARY'" >&2
  exit 2
fi

if [[ "$PATCH_MODE" != "patched" && "$PATCH_MODE" != "vanilla" ]]; then
  echo "❌ 无效 --patch-mode: $PATCH_MODE" >&2
  exit 2
fi

if [[ "$ARCHITECTURE_ONLY" == 1 && -z "$TARGET" ]]; then
  echo "❌ --architecture-only 需要 --target" >&2
  exit 2
fi

export LC_ALL=C
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BINARY="$(cd -- "$(dirname -- "$BINARY")" && pwd)/$(basename -- "$BINARY")"
COMMAND=("$BINARY")
if [[ -n "$RUNNER" ]]; then
  # The fixtures change directories before launching the binary.
  RUNNER="$(command -v -- "$RUNNER" || printf '%s' "$RUNNER")"
  if [[ "$RUNNER" == */* && "$RUNNER" != /* ]]; then
    RUNNER="$PWD/$RUNNER"
  fi
  COMMAND=("$RUNNER" "$BINARY")
fi

PASS=0
FAIL=0
SKIP=0

record() {
  local status="$1" label="$2"
  case "$status" in
    PASS) PASS=$((PASS + 1)); echo "  ✅ $label" ;;
    SKIP) SKIP=$((SKIP + 1)); echo "  ⏭️ $label" ;;
    FAIL) FAIL=$((FAIL + 1)); echo "  ❌ $label" ;;
  esac
}

summary() {
  echo ""
  echo "测试汇总  ✅ $PASS 通过 / ⏭️ $SKIP 跳过 / ❌ $FAIL 失败"
  [[ "$FAIL" -eq 0 ]]
}

echo "二进制：$BINARY"
echo "Runner：${RUNNER:-原生执行}  /  目标：${TARGET:-未指定}  /  模式：$PATCH_MODE"

# file and readelf inspect the binary without executing it, including foreign architectures.
FILE_OUTPUT="$(file -b "$BINARY")"
echo "  file: $FILE_OUTPUT"

if [[ -n "$TARGET" ]]; then
  case "$TARGET" in
    *x86_64*mingw*|*x86_64*windows*) ARCH_PATTERN='PE32\+.*x86-64' ;;
    *i686*mingw*|*i686*windows*) ARCH_PATTERN='PE32 executable.*Intel (80386|i386)' ;;
    *aarch64*mingw*|*arm64*windows*) ARCH_PATTERN='PE32\+.*(Aarch64|ARM64)' ;;
    *x86_64*darwin*|*macos*x86_64*) ARCH_PATTERN='Mach-O.*x86_64' ;;
    *darwin*|*macos*) ARCH_PATTERN='Mach-O.*arm64' ;;
    *x86_64*linux*|*linux*x86_64*|*x86_64-musl*) ARCH_PATTERN='ELF 64-bit.*x86-64' ;;
    *aarch64*linux*|*linux*aarch64*|*aarch64-musl*) ARCH_PATTERN='ELF 64-bit.*(aarch64|ARM64)' ;;
    *i686*linux*|*i686-musl*|i?86*) ARCH_PATTERN='ELF 32-bit.*(Intel (80386|i386)|x86)' ;;
    *armv7*) ARCH_PATTERN='ELF 32-bit.*ARM.*EABI5' ;;
    *arm-unknown*|*arm-linux*) ARCH_PATTERN='ELF 32-bit.*ARM' ;;
    *loongarch64*) ARCH_PATTERN='ELF 64-bit.*LoongArch' ;;
    *mips64el*) ARCH_PATTERN='ELF 64-bit LSB.*MIPS' ;;
    *mips64*) ARCH_PATTERN='ELF 64-bit MSB.*MIPS' ;;
    *mipsel*) ARCH_PATTERN='ELF 32-bit LSB.*MIPS' ;;
    *mips*) ARCH_PATTERN='ELF 32-bit MSB.*MIPS' ;;
    *) ARCH_PATTERN="" ;;
  esac
  if [[ -n "$ARCH_PATTERN" ]] && grep -qiE "$ARCH_PATTERN" <<< "$FILE_OUTPUT"; then
    record PASS "架构与目标 $TARGET 匹配"
  else
    record FAIL "无法确认架构与目标 $TARGET 匹配"
  fi
else
  record SKIP "架构匹配，未指定 --target"
fi

case "$FILE_OUTPUT" in
  ELF*)
    if LINKAGE="$(readelf -Wl -d "$BINARY" 2>&1)"; then
      if grep -qE '^[[:space:]]*INTERP([[:space:]]|$)|\(NEEDED\)' <<< "$LINKAGE"; then
        if [[ "$REQUIRE_STATIC" == 1 || "$LITE_MODE" == 0 ]]; then
          record FAIL "ELF 静态链接检查，发现动态加载器或共享库"
        else
          record PASS "Lite ELF 动态链接"
        fi
      else
        record PASS "ELF 静态链接，无动态加载器或共享库"
      fi
      if ! grep -qE '^[[:space:]]*GNU_STACK[[:space:]]' <<< "$LINKAGE"; then
        record FAIL "ELF 缺少 GNU_STACK 段，无法确认 NX"
      elif grep -qE '^[[:space:]]*GNU_STACK[[:space:]].*[[:space:]][RWE]*E[RWE]*[[:space:]]' <<< "$LINKAGE"; then
        record FAIL "ELF 堆栈可执行（缺少 noexecstack 硬化）"
      else
        record PASS "ELF 非可执行堆栈（NX）检查"
      fi
    else
      record FAIL "无法检查 ELF 链接信息：$LINKAGE"
    fi ;;
  PE32*|Mach-O*)
    if [[ "$REQUIRE_STATIC" == 1 ]]; then
      record FAIL "--require-static 需要 ELF 产物"
    fi ;;
  *)
    record FAIL "无法识别二进制格式" ;;
esac

if [[ "$ARCHITECTURE_ONLY" == 1 ]]; then
  record SKIP "运行时测试，未提供该目标的执行环境"
  summary
  exit $?
fi

if VERSION_OUTPUT="$("${COMMAND[@]}" --version 2>&1)" &&
    grep -qE '^aria2 version [0-9]' <<< "$VERSION_OUTPUT"; then
  record PASS "${VERSION_OUTPUT%%$'\n'*}"
else
  record FAIL "无法执行 aria2 --version：$VERSION_OUTPUT"
  summary
  exit 1
fi

check_default() {
  local name="$1" expected="$2" help_text="${3:-$HELP_OUTPUT}" value
  value="$(awk -v option="--$name" '
    {gsub(/\r/, "")}
    /^ (-[[:alpha:]], )?--/ {
      if (found) exit
      found = ($0 ~ "^ (-[[:alpha:]], )?" option "([=[]|[[:space:]])")
    }
    found && /^[[:space:]]*Default:/ {print $2; exit}
  ' <<< "$help_text")"
  if [[ "$value" == "$expected" ]]; then
    record PASS "--$name 默认值为 $expected"
  else
    record FAIL "--$name 默认值期望 $expected，实际为 ${value:-未知}"
  fi
}

if [[ "$PATCH_MODE" == "patched" ]]; then
  HELP_OUTPUT="$("${COMMAND[@]}" --help 2>&1)"
  HTTP_HELP_OUTPUT="$("${COMMAND[@]}" --help=#http 2>&1)"
  check_default max-connection-per-server 16 "$HELP_OUTPUT"
  check_default max-concurrent-downloads 16 "$HELP_OUTPUT"
  check_default split 128 "$HELP_OUTPUT"
  check_default min-split-size 1M "$HELP_OUTPUT"
  check_default continue true "$HELP_OUTPUT"
  check_default connect-timeout 30 "$HTTP_HELP_OUTPUT"
  check_default retry-wait 1 "$HTTP_HELP_OUTPUT"
fi

run_fixture() {
  local label="$1" script="$2"
  shift 2
  if python3 "$SCRIPT_DIR/$script" "$BINARY" --runner "$RUNNER" "$@"; then
    record PASS "$label"
  else
    record FAIL "$label"
  fi
}

has_feature() {
  grep -qE "^Enabled Features: ([^,]+, )*$1([[:space:],]|$)" <<< "$VERSION_OUTPUT"
}

test_feature() {
  local feature="$1" label="$2" script="$3"
  if has_feature "$feature"; then
    if [[ "$PATCH_MODE" == "vanilla" ]]; then
      run_fixture "$label" "$script" --baseline
    else
      run_fixture "$label" "$script"
    fi
  elif [[ "$LITE_MODE" == 1 ]]; then
    record SKIP "$label，Lite 构建未启用 $feature"
  else
    record FAIL "$label，构建缺少 $feature"
  fi
}

# Loopback checks are release gates and need no public network access.
echo ""
echo "本地功能测试"
run_fixture "HTTP 下载、分片、续传与重试" test-http-reliability.py --patch-mode "$PATCH_MODE"
test_feature GZip "HTTP 压缩内容解码" test-http-encoding.py
test_feature BitTorrent "BitTorrent 校验与分片请求" test-bittorrent.py
# The fixture supplies a CA file, while AppleTLS uses the system keychain.
if grep -qE '^Libraries: (.*[[:space:]])?AppleTLS([[:space:]]|$)' <<< "$VERSION_OUTPUT"; then
  record SKIP "HTTPS 本地证书校验，AppleTLS 使用系统钥匙串"
else
  test_feature HTTPS "HTTPS 本地证书校验" test-http-tls.py
fi

# External connectivity is optional, including when the binary lacks TLS support in a Lite build.
TMPDIR_TEST="$(mktemp -d)" || exit 1
trap 'rm -rf -- "$TMPDIR_TEST"' EXIT
if ! has_feature HTTPS; then
  if [[ "$LITE_MODE" == 1 ]]; then
    record SKIP "公网 HTTPS，Lite 构建未启用 HTTPS"
  else
    record FAIL "构建缺少 HTTPS"
  fi
elif (cd -- "$TMPDIR_TEST" &&
      "${COMMAND[@]}" --no-conf --out=authors --max-tries=1 --timeout=10 \
        --connect-timeout=10 --summary-interval=0 \
        https://raw.githubusercontent.com/aria2/aria2/master/AUTHORS >/dev/null 2>&1) &&
    [[ -s "$TMPDIR_TEST/authors" ]]; then
  record PASS "公网 HTTPS 下载"
else
  record SKIP "公网 HTTPS 未验证"
fi

summary
