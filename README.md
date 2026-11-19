# aria2_build

Aria2 的跨平台构建和增强补丁仓库。Full 提供静态 Linux、Windows 和动态链接的 Apple Silicon 产物。Lite 使用 Ubuntu 系统依赖，适合 Linux 快速构建与验证。两条流水线共享上游提交、补丁应用和源码归档流程。

[功能来源、取舍与验证](docs/feature-inventory.md) · [源码、署名与依赖](docs/distribution.md)

## 支持的目标

| 流水线 | 目标 | TLS 后端 | 产物 |
|---|---|---|---|
| Full | Linux x86_64、i686、aarch64、arm、armv7、loongarch64、mips、mipsel、mips64、mips64el | OpenSSL 或 LibreSSL | `*_static.zip`，musl 静态 |
| Full | Windows x86_64、i686 | OpenSSL 或 LibreSSL | `*_static.zip`，MinGW |
| Full | macOS arm64 | AppleTLS | `*-macos-dynamic.zip` |
| Lite | Linux x86_64、aarch64 | OpenSSL | `*-lite`，可选静态或动态 |

## 构建与发布

在 GitHub Actions 中选择 **Aria2 Full Build** 或 **Aria2 Lite Build**，然后使用 **Run workflow**。

| 参数 | 流水线 | 含义 |
|---|---|---|
| `aria2_ref` | Full / Lite | 留空使用 [`build-aux/aria2.commit`](build-aux/aria2.commit)。也接受上游分支、标签、完整提交 SHA 或 `1.37.0` 这样的版本号 |
| `patch_mode` | Full / Lite | `patched` 应用补丁队列，`vanilla` 保留上游源码。默认 `patched` |
| `target` | Full / Lite | `all` 或指定目标。Full 默认 `all`，Lite 手动默认 `linux-x86_64` |
| `enable_zlib_ng` | Full | 静态交叉构建使用 zlib-ng，默认启用 |
| `enable_libressl` | Full | 静态交叉构建使用 LibreSSL，默认关闭 |
| `enable_static` | Lite | 静态链接，默认启用 |
| `extra_configure_flags` | Lite | 可选的 `configure` 参数，以空格分隔 |

每次构建先解析并锁定一次上游提交。所有目标使用同一份通过 SHA-256 校验的源码归档。增强模式会在任何补丁应用失败时停止。使用其他上游版本时，可以使用 `vanilla` 避免补丁版本约束。Full 的直接下载依赖和交叉工具链由 [依赖锁](build-aux/dependencies.tsv) 和 [镜像锁](build-aux/toolchains.tsv) 管理。

- 默认分支推送和 PR 构建常用目标，产物保存在 Actions。手动构建可覆盖单一目标。
- 定时运行验证全矩阵，验证通过后更新 `continuous` / `continuous-lite`。默认分支上使用全部默认构建参数的手动全目标运行也可更新对应预发布。
- Full 的 Release 触发器使用现有发布标签解析上游版本，并把验证过的产物附加到该发布。产物包括二进制、对应 Aria2 源码、构建信息和 `SHA256SUMS`。

## 增强功能

- **并发与续传**。解除单服务器 16 连接上限，保留偏并行的增强默认值。慢速、断连和 HTTP 异常可以按策略重试。
- **HTTP 重试策略**。`--retry-on-400`、`--retry-on-403`、`--retry-on-406` 各自控制对应状态码，`--retry-on-unknown` 控制其他未单独处理的错误。重试遵守 `--retry-wait`、`--max-tries`，429 和 503 还支持 `Retry-After`。服务端指定的额外等待最长 600 秒。
- **HTTP 传输兼容性**。支持 `deflate` 声明的裸 DEFLATE，并校验分块 206 的 Content-Range 和解码长度。连接失败时尝试其它已解析地址。
- **BitTorrent**。新增 `--bt-piece-selector=inorder`，按 piece 编号选择当前可用的数据。默认保持原策略，常规下载阶段的 `--bt-prioritize-piece` 仍优先。增强版也会检查 metainfo 的 piece 长度、哈希边界和内部存储类型。
- **原有平台定制**。保留当前目录配置与 DHT 默认路径、MinGW daemon 和 Windows 系统识别补丁。

| 选项 | 原版 | 增强版 |
|---|---:|---:|
| `--max-connection-per-server` | 1（最高 16） | 16（解除上限） |
| `--max-concurrent-downloads` | 5 | 16 |
| `--min-split-size` | 20M | 1M |
| `--split` | 5 | 128 |
| `--continue` | false | true |
| `--connect-timeout` | 60 秒 | 30 秒 |
| `--retry-wait` | 0 秒 | 1 秒 |

## 本地构建与测试

使用与 CI 相同的镜像构建 Linux x86_64。其它目标可从镜像锁中查找。

```bash
image=$(awk -F '\t' '$1 == "x86_64-unknown-linux-musl" { print $2 }' build-aux/toolchains.tsv)
docker run --rm -v "$PWD:/build" -e BUILD_OUTPUT_DIR=/build/out "$image" /build/build.sh
./scripts/test.sh out/aria2c --target x86_64-unknown-linux-musl --require-static
```

本地脚本支持 `--patch-mode vanilla`、`--runner wine`、`--runner qemu-aarch64`。测试覆盖架构、ELF 链接方式、默认值、本地 HTTP Range、SHA-256、断线续传、重试时序、压缩和 BitTorrent。运行时测试缺少执行环境时，MIPS 和部分 LoongArch 产物仅验证架构和链接。公开网络 HTTPS 探测允许跳过，回环测试失败会阻断对应构建。

用相同连接数、数据和延迟比较多个构建。

```bash
python3 scripts/benchmark-http.py \
  /path/to/vanilla/aria2c /path/to/patched/aria2c
```

补丁和构建历史来自 [aria2](https://github.com/aria2/aria2)、[DoTheBetter](https://github.com/DoTheBetter/aria2_build)、[abcfy2](https://github.com/abcfy2/aria2-static-build)、[myfreeer](https://github.com/myfreeer/aria2-build-msys2) 及 [P3TERX](https://github.com/P3TERX/Aria2-Pro-Core)。新增和候选功能的源码引用见[功能对照表](docs/feature-inventory.md)。
