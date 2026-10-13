# aria2_build

基于 [DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build) / [abcfy2/aria2-static-build](https://github.com/abcfy2/aria2-static-build) 的精简定制版。**核心差异：构建参数可由用户在 GitHub Actions 界面自定义**（目标平台、aria2 版本、是否 zlib-ng / LibreSSL 等），保留 aria2 源码级魔改补丁，**并内置从构建到测试的完整自动化流水线**。

- 📄 设计方案：[docs/build-system-design.md](docs/build-system-design.md)
- 📋 待办清单：[docs/TODO.md](docs/TODO.md)
- 🔍 代码审查：[docs/code-review.md](docs/code-review.md)
- 🤖 AI 助手上下文：[AGENTS.md](AGENTS.md)

---

## 支持的目标平台

| TLS 后端 | 平台 | 产物后缀 |
|----------|------|----------|
| OpenSSL | Linux x86_64 / i686 / aarch64 / arm / armv7 / loongarch64 / mips / mipsel / mips64 / mips64el (musl 静态) | `*_static.zip` |
| WinTLS  | Windows x86_64 / i686 (mingw 静态) | `*_static.zip` |
| AppleTLS| macOS arm64 (动态链接) | `*-macos-dynamic.zip` |
| OpenSSL | Linux x86_64 / aarch64（lite 模式，系统包快速编译） | `*-lite` |

---

## 如何触发构建

所有 workflow 都在 **GitHub → Actions** 页面手动 `Run workflow` 触发，也可由定时任务 / Release 事件自动触发。

### 1. Full 构建（全平台静态，推荐用于发布）

Workflow：`.github/workflows/full.yml`

输入参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `aria2_ref` | aria2 源码版本（tag 如 `1.37.0`，或 branch/commit） | `master` |
| `target` | 目标平台；留空或 `all` = 构建全部 | `all` |
| `enable_zlib_ng` | 用 zlib-ng 替代 zlib | `true` |
| `enable_libressl` | 用 LibreSSL 替代 OpenSSL | `false` |

- 触发器：`workflow_dispatch` / `schedule`（每周一 UTC 03:00）/ `release`
- 产物：每平台一个 `aria2-<ver>-<host>_static.zip`，附带 `build_info.md`
- 发版策略：定时 & 手动 → `continuous` 预发布 tag；Release 事件 → `v<aria2-ver>` 正式 release

### 2. Lite 构建（仅 Linux，快速验证）

Workflow：`.github/workflows/lite.yml`

输入参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `aria2_ref` | 源码 branch/tag/commit | `master` |
| `target` | `linux-x86_64` 或 `linux-aarch64` | `linux-x86_64` |
| `enable_static` | 是否静态编译 | `true` |
| `extra_configure_flags` | 附加 `configure` 参数 | （空） |

- 触发器：`workflow_dispatch` / `schedule`（每周一 UTC 03:00）
- 产物：`aria2-<ver>-<target>-lite`，发布到 `continuous-lite` 预发布 tag

---

## 自动化测试流水线（构建 → 测试 → 发布）

每次构建都会自动运行综合测试，**测试失败则不会发布**。测试由 [`scripts/test.sh`](scripts/test.sh) 驱动，覆盖：

| 测试项 | 内容 | 说明 |
|--------|------|------|
| 可执行性 | `aria2c --version` | 验证二进制能启动并输出版本 |
| 架构匹配 | `file` 命令 | 验证二进制 ELF/PE/Mach-O 架构与目标平台一致 |
| 静态链接 | `ldd` / `otool` | 验证 musl 构建为完全静态（无动态依赖） |
| **魔改默认值** | `--help` 解析 | 验证 `max-connection-per-server=16`、`split=128`、`min-split-size=1M`、`continue=true` 等补丁已生效 |
| HTTPS 下载 | 真实文件下载 | 从 GitHub 下载小文件并校验大小 |
| 多连接分片 | 16 连接下载 | 验证 `max-connection-per-server` 上限解除 + 内容一致性 |
| 断点续传 | `-c` 续传 | 验证 `continue=true` 默认启用 |

### 测试运行环境

| 产物平台 | 测试方式 |
|----------|----------|
| Linux x86_64 / i686 (musl) | 原生执行（静态 musl 二进制在 x86_64 宿主直接运行） |
| Linux aarch64 / arm / armv7 (musl) | QEMU 用户态模拟（`qemu-aarch64` / `qemu-arm`） |
| Linux loongarch64 (musl) | QEMU（若不可用则仅架构检查） |
| Linux mips / mipsel / mips64 / mips64el (musl) | 仅架构检查（运行时测试挂起，沿用上游策略） |
| Windows x86_64 / i686 (mingw) | Wine 模拟执行 |
| macOS arm64 | macOS runner 原生执行 |
| Lite x86_64 | ubuntu 原生执行 |
| Lite aarch64 | QEMU 用户态模拟 |

### 流水线阶段

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  构建（编译） │ ──→ │  综合测试    │ ──→ │  产物验证     │ ──→ │  发布     │
│  build.sh    │     │  test.sh     │     │  verify job  │     │  release │
│  (Docker/原生)│     │  (QEMU/Wine) │     │  (ZIP完整性)  │     │          │
└─────────────┘     └─────────────┘     └──────────────┘     └──────────┘
                          │                     │                   │
                          └──── 任一失败 ────────┴──── 不发布 ──────┘
```

> **关键**：`prerelease` 和 `release` job 通过 `needs:` 依赖测试和验证 job，测试不通过则不会创建发布。

---

## 魔改内容

以下补丁位于 `patch/`，构建时由 `build.sh` / workflow 自动 `patch -p1` 应用到 aria2 源码：

1. **`max-connection-per-server`** —— 上限改为 `*`（无限），默认值改为 `16`。允许更高并发提升下载速度。
2. **`min-split-size`** —— 最小值改为 `1K`，默认值改为 `1M`。允许更精细分片。
3. **`piece-length`** —— 最小值改为 `1K`，默认值改为 `1M`。
4. **`connect-timeout`** —— 默认值改为 `30` 秒，避免慢网下过早放弃连接。
5. **`split`** —— 默认值改为 `128`，提高并发分片数。
6. **`continue`** —— 默认值改为 `true`，默认启用断点续传。
7. **`retry-wait`** —— 默认值改为 `1` 秒，更快恢复。
8. **`max-concurrent-downloads`** —— 默认值改为 `16`。
9. **`netrc-path` / `conf-path` / `dht-file-path` / `dht-file-path6`** —— 默认路径改为当前目录，避免与系统文件冲突。
10. **`daemon`** —— 使其在 MinGW（Windows）环境下可用。
11. **慢速/断连自动重试** —— 提高网络波动下的稳定性。
12. **`retry-on-400` / `retry-on-403` / `retry-on-406`** —— 对应 HTTP 4xx 错误自动重试（仅 `retry-wait > 0` 时生效）。

### 默认值变化一览

| 选项 | 原版 | 魔改后 |
|------|------|--------|
| `--max-connection-per-server` | `1`（上限 16） | `16`（**上限无限制**） |
| `--max-concurrent-downloads` | `5` | `16` |
| `--min-split-size` | `20M` | `1M` |
| `--split` | `5` | `128` |
| `--continue` | `false` | `true` |
| `--connect-timeout` | `60s` | `30s` |
| `--retry-wait` | `0s` | `1s` |

> 详细补丁文件见 `patch/aria2-000{1..6}-*.patch`。

---

## 本地构建与测试

### Docker 复现 CI 构建

```bash
# 复现 full 模式的某个目标平台（以 x86_64-linux-musl 为例）
docker run --rm -v "$(git rev-parse --show-toplevel):/build" \
  ghcr.io/abcfy2/musl-cross-toolchain-ubuntu:x86_64-unknown-linux-musl \
  /build/build.sh
```

环境变量（与 workflow 一致）：`CROSS_HOST` / `USE_ZLIB_NG` / `USE_LIBRESSL` / `ARIA2_VER`。

### 本地运行测试脚本

```bash
# 测试原生 Linux 二进制
./scripts/test.sh ./aria2c --target x86_64-unknown-linux-musl

# 测试 Windows 二进制（需安装 Wine）
./scripts/test.sh ./aria2c.exe --runner wine --target x86_64-w64-mingw32

# 测试 aarch64 二进制（需安装 qemu-user-static）
./scripts/test.sh ./aria2c --runner qemu-aarch64-static --target aarch64-unknown-linux-musl
```

---

## 感谢

- https://github.com/aria2/aria2
- https://github.com/DoTheBetter/aria2_build
- https://github.com/abcfy2/aria2-static-build
- https://github.com/P3TERX/Aria2-Pro-Core
- https://github.com/myfreeer/aria2-build-msys2
- https://git.q3aql.dev/q3aql/aria2-static-builds
