# aria2_build

Aria2 跨平台自动化构建与增强补丁仓库，提供 **Full**（Linux 和 Windows 静态链接、macOS 动态链接）与 **Lite**（Linux 快速构建与回归验证）两条构建流水线。Fork 自 [DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build)。

## 自动更新、HTTPS 与自定义构建

- **上游自动同步**。每天检查上游 `master` 和正式标签，也可在 Actions 手动启动 **Sync upstream Aria2**。候选提交必须通过补丁应用、Lite CppUnit 与回环测试、Full 全平台构建与测试及产物校验，才能写回源码锁并发布。新正式标签优先发布正式版，只有 `master` 更新时发布 `continuous` 预发布。失败详情汇总到仓库 Issue。[上游仓库](https://github.com/aria2/aria2)
- **Windows OpenSSL 开箱即可下载 HTTPS**。保留解压后与 `aria2c.exe` 同目录的 `cacert.pem` 即可。CA 按 `--ca-certificate`、`SSL_CERT_FILE`、程序同目录的 `cacert.pem`、OpenSSL 默认路径的优先级选取，文件缺失时自动回退到下一项。WinTLS 构建使用 Windows 证书库。
- **Full 支持自定义构建**。可选择 TLS 后端、按编号排除补丁、传入额外的 configure 参数和选择编译优化级别。设置 `run_tests=false` 只生成构建产物，发布任务会跳过。见下方[构建参数](#github-actions-构建参数)。

> 延伸阅读：[功能来源、取舍与验证](docs/feature-inventory.md) · [源码、署名与依赖](docs/distribution.md)

## 核心特性（与原版相比做了哪些增强？）

### 1. 下载更快、开箱即用（默认参数调优）

原版 Aria2 的默认设置偏保守，不仅限制了单服务器最多 16 线程，很多加速参数也默认关闭。本仓库直接解除了单服务器连接数上限，并把常用提速配置设为默认值——**不用自己折腾复杂配置文件，下载就能跑得更稳更快**：

| 选项 | 上游默认值 | 本仓库默认值 | 通俗说明 |
| --- | --- | --- | --- |
| `--max-connection-per-server` | `1`（上限 `16`） | `16`（无上限） | 取消单服务器最多 16 线程的限制，支持更高并发 |
| `--max-concurrent-downloads` | `5` | `16` | 最多同时下载 16 个任务，队列不用干等 |
| `--min-split-size` | `20M` | `1M` | 文件大于 1MB 就能切分多线程，小文件也能加速 |
| `--split` | `5` | `128` | 单个任务默认最多拆成 128 块并发下载 |
| `--continue` | `false` | `true` | 默认开启断点续传，意外中断后无需重头再来 |
| `--connect-timeout` | `60s` | `30s` | 连不上时更快判定超时，减少死等 |
| `--retry-wait` | `0s` | `1s` | 遇到临时失败时默认等 1 秒自动重试，不再直接报错退出 |

### 2. 断流更少、网盘与限流环境更稳（HTTP 稳定性与兼容性）

- **遇到临时报错或卡死自动重连**：部分网盘、图床或 CDN 偶尔会返回 `400`、`403`、`406` 或未知错误，或者下到一半掉速、连接被重置。本仓库新增了 `--retry-on-400`、`--retry-on-403`、`--retry-on-406`、`--retry-on-unknown` 重试开关，并在低速卡死或断线时自动触发重试，减少下载半途而废。
- **听懂服务器“请稍后再试”的提示**：当服务器返回 `429`（请求太频繁）或 `503`（服务暂不可用）并附带 `Retry-After` 等待时间时，Aria2 会结合 `--retry-wait` 按服务器要求等待（最长 600 秒）后再继续，避免盲目狂刷导致 IP 被彻底封禁。
- **压缩、文件名与续传兼容性**。支持原始 DEFLATE（raw `deflate`）解压，允许 `Content-Disposition` 以分号结尾（`0019`），并校验分块 `206` 响应的范围与解码后长度。
- **一个 IP 连不上自动换备用 IP**：当目标域名解析出多个 IP 地址时，当前地址连接失败会自动切换到其他可用地址继续尝试。

### 3. BT 下载更好用（BitTorrent 增强）

- **支持“边下边播”顺序下载**：新增 `--bt-piece-selector=inorder` 与 `--bt-prioritize-piece` 支持，可按从头到尾的顺序优先下载分片，下载视频类种子时更方便预览或边下边看。
- **拦截异常种子，防止崩溃**：读取种子文件（metainfo）时加强对分片长度、哈希边界及内部字段类型的校验，避免异常种子导致程序崩溃或写入错误。
- **显示种子私有标记**。`aria2c -S` 显示 `Private: yes` 或 `Private: no`（`0022`），便于在提交任务前检查种子属性。

### 4. 安全修复、便携体验与跨平台硬化

- **安全漏洞与 2038 溢出修复**：修复 `CVE-2026-75421`（`IOFile::getLine()` 行首 `\0` 栈下溢，补丁 `0018`）与 `ServerStatMan` 2038 年时间戳 32 位溢出（补丁 `0020`）；集成 Nettle 4.0 编译兼容补丁（`0017`）。
- **配置与缓存放在当前目录，拷走即用**：默认将 `.netrc`、配置文件及 DHT 缓存路径改到当前工作目录，打包到 U 盘或便携文件夹时不用再到处翻找系统隐藏目录。
- **Windows 构建**。修正 MinGW `--daemon` 的 `CreateProcessW` 参数初始化和错误诊断，并改进 Windows 版本信息。Windows OpenSSL 构建自动读取随包附带、经 SHA-256 校验的 Mozilla `cacert.pem`（`0023`）。`aria2c --version` 显示 OpenSSL 3.x 的完整运行库版本（`0024`）。WinTLS 在握手完成前校验服务器证书链、主机名和服务端用途（`0025`）。内置 `longPathAware` 清单在支持该机制的 Windows 上还需要系统启用 `LongPathsEnabled`。[微软长路径说明](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)
- **macOS `arm64` 构建**。使用系统 AppleTLS 和 Homebrew 动态库。运行所需的库及其版本见对应产物 `build_info.md` 的 `brew list` 和 `otool -L` 输出。
- **编译安全硬化**。Full 的 Linux 和 Windows 静态构建启用 `-fstack-protector-strong`、`-Wformat -Werror=format-security`，Linux ELF 额外使用 `-Wl,-z,relro,-z,now -Wl,-z,noexecstack`。

## 支持平台与构建产物

GitHub Actions 的 Full 和 Lite 共用源码准备流程。独立的 `check-dependencies.yml` 每周巡检依赖版本。

| 流水线 | 适用平台与架构 | TLS / 链接方式 | 产物格式 |
| --- | --- | --- | --- |
| **Full** | Linux：`x86_64`、`i686`、`aarch64`、`arm`、`armv7`、`loongarch64`、`mips`、`mipsel`、`mips64`、`mips64el` | OpenSSL 或 LibreSSL（musl 静态链接） | `*_static.zip` |
| **Full** | Windows：`x86_64`、`i686` | OpenSSL、LibreSSL 或 WinTLS（MinGW 静态链接，含 `longPathAware` 清单）。OpenSSL 和 LibreSSL ZIP 附带 `cacert.pem` | `*_static.zip`、`*_static_wintls.zip` |
| **Full** | macOS：`arm64` | AppleTLS（依赖 Homebrew 动态库） | `*-arm64-macos-dynamic*.zip` |
| **Lite** | Linux：`x86_64`、`aarch64` | OpenSSL（基于 Ubuntu 系统依赖，支持静态/动态） | `*-lite` |

> `build-aux/aria2.commit` 固定上游提交。Full 的 Linux、Windows 交叉构建使用 `build-aux/dependencies.tsv` 和 `build-aux/toolchains.tsv` 锁定下载依赖与容器镜像。macOS 和 Lite 则在构建时使用 Homebrew 或发行版提供的依赖。

## GitHub Actions 构建参数

手动触发工作流时支持以下输入参数：

| 参数 | 说明 | 默认值 / 可选值 |
| --- | --- | --- |
| `aria2_ref` | 上游 Aria2 的分支、标签或 Commit SHA | 默认读取 `build-aux/aria2.commit` |
| `patch_mode` | 是否应用本仓库补丁 | `patched`（默认）/ `vanilla` |
| `target` | 指定构建目标三元组 | 留空则按矩阵构建 |
| `enable_zlib_ng` | Full 的 Linux/Windows 目标是否使用 `zlib-ng` 替代 `zlib` | 默认开启 |
| `tls_backend` | Full 的 Linux/Windows TLS 后端。选择 `wintls` 时，Linux 仍使用 OpenSSL，macOS 始终使用 AppleTLS | `openssl`（默认）/ `libressl` / `wintls` |
| `exclude_patches` | Full 的 `patched` 模式中按四位编号排除补丁，例如 `0001,0022`。保留的补丁仍须按顺序应用成功 | 空 |
| `extra_configure_flags` | Full 和 Lite 传给 `./configure` 的额外参数。Full 支持带引号的参数值 | 空 |
| `compiler_opt` | Full 的 C/C++ 优化级别 | `-O2`（默认）/ `-O3` / `-Os` |
| `run_tests` | Full 是否执行测试。关闭时仍校验产物归档并生成校验和 | `true`（默认）/ `false` |
| `enable_static` | Lite 流水线是否启用静态链接 | Lite 默认开启 |

## 本地构建与测试

### 1. 本地容器化构建（Full）

借助 `build-aux/toolchains.tsv` 中锁定的 `ghcr.io/abcfy2/*` 工具链镜像，可在本地通过 Docker 调用 `build.sh` 执行静态交叉编译：

```bash
docker run --rm -v "$PWD:/work" -w /work \
  -e CROSS_HOST=x86_64-unknown-linux-musl \
  -e PATCH_MODE=patched \
  -e USE_ZLIB_NG=1 \
  -e TLS_BACKEND=openssl \
  <toolchain-image> ./build.sh
```

常用环境变量：

- `CROSS_HOST` / `CROSS_ROOT`：目标三元组与交叉编译工具链根目录。
- `PATCH_MODE`：`patched`（应用 `patch/*.patch`）或 `vanilla`（纯净上游源码）。
- `USE_ZLIB_NG` 控制是否使用 `zlib-ng`，`TLS_BACKEND` 选择 TLS 后端。旧版脚本的 `USE_LIBRESSL` 在未指定 `TLS_BACKEND` 时仍可使用。
- `EXCLUDE_PATCHES`、`EXTRA_CONFIGURE_FLAGS`、`COMPILER_OPT` 对应 Full 的同名构建输入。测试时可给 `scripts/test.sh` 传入同一份 `--exclude-patches` 列表。
- `RUN_TESTS=false` 可跳过运行时测试及测试运行器安装。也可用 `RUN_TESTS=true INSTALL_TEST_RUNNERS=0` 复用预装的 QEMU 或 Wine。
- `BUILD_OUTPUT_DIR` 可为不同构建变体指定各自的输出目录。
- `USE_CHINA_MIRROR`：设为 `1` 可在容器内切换 Ubuntu CERNET 镜像加速 apt 包安装。

### 2. 自动化回归测试与性能基准

仓库内置本地回环测试套件（覆盖 HTTP、压缩、BT 与本地自签名 TLS 证书校验）与 HTTP 基准测试脚本，无需外网即可验证核心补丁行为：

```bash
# 运行完整测试套件（支持通过 --runner 指定 qemu-aarch64 或 wine）
./scripts/test.sh /path/to/aria2c --target <target> --patch-mode patched

# Lite 模式或校验静态链接属性
./scripts/test.sh /path/to/aria2c --lite --require-static

# 对比不同 aria2c 二进制的 HTTP/1.1 并发与吞吐表现
python3 scripts/benchmark-http.py <aria2c-binary-1> [<aria2c-binary-2> ...]

# 检查锁定依赖是否有上游新版本
python3 scripts/check-dependencies.py
```

## 仓库结构

| 路径 | 职责说明 |
| --- | --- |
| `build.sh` | Full 流水线核心静态交叉编译脚本（依次构建静态依赖、嵌入 Windows 清单、打补丁、编译并生成 `build_info.md`） |
| `build-aux/` | 上游源码与正式标签锁、依赖及工具链校验锁和 Windows 长路径清单 |
| `patch/` | 功能、安全、稳定性与兼容性增强补丁（`0001`–`0025`） |
| `scripts/` | 源码准备与归档、依赖拉取与巡检（`fetch-dependency.sh`、`check-dependencies.py`）、矩阵生成及测试基准脚本（`test.sh`、`test-*.py`、`benchmark-http.py`） |
| `docs/` | 构建系统设计、特性清单、代码审查与发布说明文档 |
| `.github/workflows/` | Full、Lite、上游同步、源码准备、依赖巡检及仓库维护工作流 |

## 致谢与源码参考

本项目的补丁集与跨平台构建方案借鉴并整合自以下开源项目：[aria2](https://github.com/aria2/aria2)、[DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build)、[abcfy2/aria2-static-build](https://github.com/abcfy2/aria2-static-build)、[myfreeer/aria2-build-msys2](https://github.com/myfreeer/aria2-build-msys2) 及 [P3TERX/Aria2-Pro-Core](https://github.com/P3TERX/Aria2-Pro-Core)。新增及候选功能的具体源码出处与取舍说明，请参阅[功能对照表](docs/feature-inventory.md)与[源码、署名与依赖](docs/distribution.md)。
