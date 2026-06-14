# aria2_build

基于 [DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build) / [abcfy2/aria2-static-build](https://github.com/abcfy2/aria2-static-build) 的精简定制版。**核心差异：构建参数可由用户在 GitHub Actions 界面自定义**（目标平台、aria2 版本、是否 zlib-ng / LibreSSL 等），并保留 aria2 源码级魔改补丁。

- 📄 设计方案：[docs/build-system-design.md](docs/build-system-design.md)
- 📋 待办清单：[docs/TODO.md](docs/TODO.md)
- 🔍 代码审查：[docs/code-review.md](docs/code-review.md)
- 🤖 AI 助手上下文：[AGENTS.md](AGENTS.md)

---

## 支持的目标平台

| TLS 后端 | 平台 | 产物后缀 |
|----------|------|----------|
| OpenSSL | Linux x86_64 / i686 / aarch64 / arm / armv7 / loongarch64 (musl 静态) | `*_static.zip` |
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

> ⚠️ Lite 模式 aarch64 需自行确认交叉工具链可用，详见 [docs/code-review.md](docs/code-review.md) §5。

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

> 详细补丁文件见 `patch/aria2-000{1..6}-*.patch`。

---

## 本地构建（Docker 复现 CI）

```bash
# 复现 full 模式的某个目标平台（以 x86_64-linux-musl 为例）
docker run --rm -v "$(git rev-parse --show-toplevel):/build" \
  ghcr.io/abcfy2/musl-cross-toolchain-ubuntu:x86_64-unknown-linux-musl \
  /build/build.sh
```

环境变量（与 workflow 一致）：`CROSS_HOST` / `USE_ZLIB_NG` / `USE_LIBRESSL` / `ARIA2_VER`。

---

## 感谢

- https://github.com/aria2/aria2
- https://github.com/DoTheBetter/aria2_build
- https://github.com/abcfy2/aria2-static-build
- https://github.com/P3TERX/Aria2-Pro-Core
- https://github.com/myfreeer/aria2-build-msys2
- https://git.q3aql.dev/q3aql/aria2-static-builds
