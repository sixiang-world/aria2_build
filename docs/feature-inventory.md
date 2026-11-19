# Aria2 功能对照与验证

默认源码为上游 `9e7273583f83e881e3ec067b523ba88724088d2f`。`patched` 和 `vanilla` 使用同一来源；对照时分别应用或跳过完整补丁队列。现有六个补丁与 [myfreeer 的原补丁](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087) 一致。

## 已整合

| 功能 | 来源 | 实现 | 验证 |
|---|---|---|---|
| 连接上限、分片、并发和续传默认值 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch)、[上游 #1431](https://github.com/aria2/aria2/pull/1431) | 保留 `0002`。默认单主机 16 连接，用户可按任务提高 | 本机确认 20 路 Range 同时传输、SHA-256 及非零偏移续传 |
| 慢速、断连恢复 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch) | 保留 `0003`，复用原有重试与分片机制 | 回环服务先限速或中止响应体，再返回成功，成品 SHA-256 一致 |
| 4xx 重试与服务端退避 | 现有 `0005`，[RFC 9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after) | `0008` 让专用开关优先，保留退出码，重试遵守 `retry-wait` 与 `max-tries`；429/503 接受秒数和 HTTP 日期，服务端额外等待限 600 秒。`0015` 修正等待中的同 URL 请求被重复计入连接数的问题 | 回环验证开关、状态码、重试时序和次数。CppUnit 对照验证正在等待的请求保持计数、唤醒时间及选择顺序 |
| 裸 DEFLATE | [Elypha 0007](https://github.com/Elypha/aria2-mod/blob/941a5db1c7f3e6e26249aeceedbf7023a8d0aa36/aria2-patch/0007-retry-raw-deflate-mode.patch)、[上游 #2268](https://github.com/aria2/aria2/pull/2268) | `0007` 在写入前识别 zlib/gzip 封装或裸流，保持校验错误为失败 | 本机 7 项，覆盖裸流、gzip、zlib、跨块头部和损坏校验和。原版对照拒绝裸流。头部恰好匹配 zlib 签名的裸流按 zlib 处理 |
| 分块 206 续传 | [Motrix d5e6f8ae](https://github.com/motrixapp/aria2/commit/d5e6f8aee6de4d03e94aec9af3b3efac5aff06bc)、[上游 #1115](https://github.com/aria2/aria2/issues/1115) | `0012` 保留合法 `Content-Range`，在消费响应前校验起点和范围；解码器处理跨 piece 的块并校验总长度 | 有前缀的回环续传通过 SHA-256。缺失、错位、忽略 Range、短响应体和过长分块用例按预期失败，已有前缀保持完整 |
| 备用 IP 连接 | [Motrix #33](https://github.com/motrixapp/aria2/pull/33) | `0013` 等待或连接失败后尝试已解析的其它地址，修正备用 IPv4 超时分支 | CppUnit 使用真实本地套接字和模拟的异常通知，原版对照未切换，补丁后选择缓存的下一地址。Windows 实机仍待验证 |
| BT 顺序请求 | [上游 #1671](https://github.com/aria2/aria2/pull/1671) | `0010` 增加可选 `--bt-piece-selector=inorder`，复用上游位图；默认保留随机选择，常规阶段显式优先项仍优先 | 回环 tracker 和 peer 验证默认、33 个 piece 顺序、尾部优先和双 peer endgame，全量 SHA-256 一致 |
| BT metainfo 与 piece 校验 | [上游 #2401](https://github.com/aria2/aria2/pull/2401)、[上游 #2372](https://github.com/aria2/aria2/pull/2372)、[Motrix #28](https://github.com/motrixapp/aria2/pull/28) | `0009` 保留原作者的类型保护。`0011` 检查 piece 长度和哈希对齐，使用无溢出的计数方式 | 通过静态编译及真实本地 BT 流程；新增 CppUnit 覆盖非法字段和合法零长度种子 |
| 本地配置、MinGW daemon 及 Windows 信息 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087) | 保留 `0001`、`0004`、`0006` | Windows 服务行为依赖实机；常用 MinGW CI 通过 Wine 运行下载测试 |
| 统一源码、依赖完整性与构建清单 | [abcfy2](https://github.com/abcfy2/aria2-static-build/tree/a9e4ba3)、[DoTheBetter](https://github.com/DoTheBetter/aria2_build/tree/47cf3a9) | 同次运行共用验证过的源码归档；SHA-256 检查下载和缓存；锁定交叉镜像、Actions 和直接下载依赖 | 整队列严格应用在默认提交和 `release-1.37.0`；归档校验及损坏校验和负对照通过。各目标运行结果见 Actions |
| libssh2 更新 | [上游 397ac69](https://github.com/libssh2/libssh2/commit/397ac69b694176cf23aff5a53dc956223cd581ab)、[上游安全公告](https://github.com/libssh2/libssh2/security/advisories) | Full 锁定 SHA-256 校验的上游开发快照，包含 1.11.1 之后的安全修复。Lite 和 macOS 分别由发行版或 Homebrew 提供修复 | Full 本机 x86_64 musl 成品通过 SFTP 回环下载、主机密钥校验和 SHA-256 |
| 测试和发布 | 本仓库 | 回环 HTTP、压缩和 BT 测试作为 CI 门禁；发布资产通过架构、链接、完整性和校验和检查 | Linux 原生已验证。没有合并草稿分支。本轮 Actions 见 [PR #1](https://github.com/sixiang-world/aria2_build/pull/1) |

## 比较过的候选

| 候选 | 核对结果与取舍 |
|---|---|
| 连接数或分片进一步放宽 | Cabbage、hguandl、kenvix、hosxy 的主要差异是移除上限或提高默认值；项目已覆盖参数能力。保留 16 连接默认值，使用到实际并发而非参数值作为测试证据。[Cabbage](https://github.com/Cabbagec/aria2-enhanced/tree/01512fc1) · [hguandl](https://github.com/hguandl/aria2-patch/tree/2fd5c3a) · [kenvix](https://github.com/kenvix/aria2-unlocked/tree/49ad22ae) · [hosxy](https://github.com/hosxy/aria2-fast) |
| 第三方 HTTP 重试补丁 | `500retry` 可用 `retry-on-unknown=true` 覆盖。无冒号或空值头部的放宽会改变解析边界。上游 #2222 的错误 Range 无条件重试可能反复请求永久不兼容的服务器。保留错误边界和显式重试开关。[onion-downloader](https://github.com/sn0b4ll/aria2-onion-downloader/tree/5e96144/downloader) · [上游 #2222](https://github.com/aria2/aria2/pull/2222) |
| Want-Digest 开关 | 上游已经有 `--no-want-digest-header`。早期 P3TERX 补丁中的默认值与现有完整性行为不同，沿用上游开关。[上游选项处理](https://github.com/aria2/aria2/blob/9e7273583f83e881e3ec067b523ba88724088d2f/src/HttpRequestCommand.cc) · [P3TERX 补丁](https://github.com/P3TERX/Aria2-Pro-Core/blob/master/patch/0004-option-add-option-to-disable-want-digest-header.patch) |
| 503 重试次数修复 | Motrix 修复的是其唤醒时重设计数的分支逻辑；本项目该路径没有重设调用，回环用例直接验证 `max-tries`。[Motrix 8077cfaf](https://github.com/motrixapp/aria2/commit/8077cfaf) |
| BT tracker 全轮询 | qydysky 方案在成功路径推进失败状态，影响 announce 生命周期；BT 去吸血类方案也改变正常 peer 行为。沿用上游策略，等待独立 HTTP/UDP tracker 测试。另有范围较小的同层轮换提案。[qydysky](https://github.com/qydysky/aria2_patch/tree/0feb0126117d334d6038bb3dc10402b4541f3669) · [aria2b](https://github.com/makeding/aria2b/tree/3eed57f) · [上游 #2157](https://github.com/aria2/aria2/pull/2157) |
| Windows ARM64 / WinTLS | Windows ARM64 有 LLVM-MinGW/UCRT 的可行实现，仍需把本仓库依赖与 ARM64 CI 整体接入。WinTLS 与 SFTP crypto/provider、证书库和最低 TLS 版本需要单独验证。Motrix 已从其默认发布移除 WinTLS 流水线。[Motrix ARM64](https://github.com/motrixapp/aria2/pull/25) · [minnyres](https://github.com/minnyres/aria2-windows-arm64/tree/08e701b09516558c8c5ef4ce314936f14e2f3575) · [Motrix TLS 构建调整](https://github.com/motrixapp/aria2/pull/18) |
| tcmalloc、jemalloc 与写缓存 | 上游已提供两种可选 allocator 的构建接口。SKIYET 主要新增打包；NFS/SMB 增大分配块的提案可能在并发下增加 RSS。暂时沿用现有内存分配策略，待长队列或网络文件系统基准验证。[SKIYET](https://github.com/SKIYET/Aria2-Static-Build-WithTCmalloc/tree/e147c0205c87ec9e9e9940ec14f3ea45b4c0db2d) · [上游 #83](https://github.com/aria2/aria2/pull/83) · [上游 #2116](https://github.com/aria2/aria2/issues/2116) |
| HTTP 自适应分段、BT v2、跨重启恢复 | aria2-next 有 libcurl/Asio 调度与 libtorrent；替换时会影响 FTP、Metalink3、libaria2 和 `.aria2` 兼容。Motrix 的强校验恢复与 SQLite 任务状态、cookie 和 RPC 改动耦合。保留现有存储和协议，采用独立可验证的兼容修复。[aria2-next](https://github.com/AnInsomniacy/aria2-next/tree/1b8fb72fc) · [Motrix #29](https://github.com/motrixapp/aria2/pull/29) |
| 其它静态构建与传输后端 | dmesg00 与 q3aql 作为工具链和发行包参考。上游 #2409 把 TLS/HTTP2 模拟作为独立传输后端，引入线程和额外依赖，不适合作为本轮默认。[dmesg00](https://github.com/dmesg00/aria2-static-builds/tree/638b1ab) · [q3aql](https://git.q3aql.dev/q3aql/aria2-static-builds) · [上游 #2409](https://github.com/aria2/aria2/pull/2409) |

## 复现验证

```bash
./scripts/test.sh /path/to/patched/aria2c --target x86_64-unknown-linux-gnu --lite --require-static
./scripts/test.sh /path/to/vanilla/aria2c --target x86_64-unknown-linux-gnu --lite --require-static --patch-mode vanilla
python3 scripts/benchmark-http.py /path/to/vanilla/aria2c /path/to/previous/aria2c /path/to/patched/aria2c
```

## 本机结果

2026-11-19 在 Linux x86_64 比较三个静态构建。上游提交、编译配置与直接链接依赖相同。每轮下载 12 MiB 固定负载，服务端每 64 KiB 间隔 4 ms，预热一轮后测量五轮。每次检查 SHA-256；四连接场景实际观测到四路同时响应。

| 构建 | 单连接中位耗时 / 吞吐 | 四连接中位耗时 / 吞吐 | 四连接进程 CPU 中位值 |
|---|---:|---:|---:|
| 上游原版 | 0.791 s / 15.17 MiB/s | 0.216 s / 55.63 MiB/s | 30.0 ms |
| 原有六个补丁 | 0.807 s / 14.86 MiB/s | 0.213 s / 56.28 MiB/s | 27.5 ms |
| 本轮增强版 | 0.789 s / 15.21 MiB/s | 0.217 s / 55.26 MiB/s | 31.9 ms |

在相同的连接数下没有观察到明显的耗时回退。四连接的单次耗时范围有重叠，小幅差异不宜外推到真实下载环境。并发的收益取决于服务器限速、网络和文件大小。

本机增强版完整 CppUnit 通过，共 930 项。两个本地发现用例需要可用的 IPv4 multicast 接口，使用 Docker bridge 运行验证。原版和增强版也分别通过独立的回环功能测试。增强版覆盖 29 个 HTTP 用例、7 个解压用例和 4 个 BT 用例。
