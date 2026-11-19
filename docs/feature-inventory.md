# Aria2 功能对照与验证

默认源码为上游 `9e7273583f83e881e3ec067b523ba88724088d2f`（截至 2026-11-18 上游 `master` 无更新提交）。`patched` 和 `vanilla` 使用同一来源；对照时分别应用或跳过完整补丁队列。

## 已整合（`patch/aria2-0001` – `0017` 与构建工程）

| 功能 | 来源 | 实现 | 验证状态 |
|---|---|---|---|
| 连接上限、分片、并发和续传默认值 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch)、[上游 #1431](https://github.com/aria2/aria2/pull/1431) | 保留 `0002`；`test.sh` 补齐 7 项调优默认值全量断言（含 `--connect-timeout=30`、`--retry-wait=1`） | 已验证（20 路 Range 并发、SHA-256 及续传） |
| 慢速、断连恢复 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch) | 保留 `0003`，复用原有重试与分片机制 | 已验证（回环限速与中断恢复） |
| 4xx 重试与服务端退避 | 现有 `0005`、[RFC 9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after) | `0008` 让专用开关优先，429/503 遵守 `Retry-After`（上限 600s）；`0015` 修正等待中请求被重复计入连接数 | 已验证（回环与 CppUnit） |
| 裸 DEFLATE | [Elypha 0007](https://github.com/Elypha/aria2-mod/blob/941a5db1c7f3e6e26249aeceedbf7023a8d0aa36/aria2-patch/0007-retry-raw-deflate-mode.patch)、[上游 #2268](https://github.com/aria2/aria2/pull/2268) | `0007` 在写入前识别封装或裸流，保持校验错误为失败 | 已验证（7 项回环解压用例） |
| 分块 206 续传 | [Motrix d5e6f8ae](https://github.com/motrixapp/aria2/commit/d5e6f8aee6de4d03e94aec9af3b3efac5aff06bc)、[上游 #1115](https://github.com/aria2/aria2/issues/1115) | `0012` + `0016` 保留合法 `Content-Range`，校验起点、范围与总长度 | 已验证（回环正/负用例） |
| 备用 IP 连接 | [Motrix #33](https://github.com/motrixapp/aria2/pull/33) | `0013` 在连接错误或 Winsock `exceptfds` 异常通知后切换备用地址，修正备用 IPv4 超时分支 | 已验证（CppUnit 本地套接字；Windows 实机待验） |
| BT 顺序请求 | [上游 #1671](https://github.com/aria2/aria2/pull/1671) | `0010` 增加可选 `--bt-piece-selector=inorder`，保留默认随机策略与显式优先项 | 已验证（回环 tracker/peer 与 endgame） |
| BT metainfo 与 piece 校验 | [上游 #2401](https://github.com/aria2/aria2/pull/2401)、[上游 #2372](https://github.com/aria2/aria2/pull/2372)（CVE-2026-71832）、[Motrix #28](https://github.com/motrixapp/aria2/pull/28) | `0009`（`dynamic_cast` 保护）+ `0011`（piece 长度与哈希对齐无溢出校验） | 已验证（静态编译、BT 回环与 CppUnit） |
| 本地配置、MinGW daemon 及 Windows 信息（Round-2 修复） | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087) + Round-2 审查修复 | `0001` 保留；**`0004` 修复 `CreateProcessW` 不可写缓冲区 UB、补齐 `si.cb = sizeof(si)`/`SW_HIDE` 与失败返回**；**`0006` 修复 `szCSDVersion` 宽字符指针输出 Bug 并新增 Windows 11 及 Server 2019/2022/2025 识别** | 补丁语法与 hunk 上下文已校验；待 MinGW CI 编译与实机验证 |
| Nettle 4.0 编译兼容（Round-2 新增） | [上游 PR #2358](https://github.com/aria2/aria2/pulls) / [openSUSE Factory](https://build.opensuse.org/projects/openSUSE:Factory/packages/aria2/files/aria2-Fix-build-with-nette4.patch?expand=0)（GPL-2.0-or-later 兼容） | **`0017`** 在 `src/LibnettleMessageDigestImpl.cc` 按 `NETTLE_VERSION_MAJOR > 3` 适配 `hash->digest` 新签名 | 精确上游 diff 已校验；待 Lite/macOS CI 验证 |
| 编译/链接安全硬化与工作流加固（Round-2 新增） | 本仓库 | `build.sh` 启用 `-fstack-protector-strong -Wformat -Werror=format-security`、Linux `-Wl,-z,relro,-z,now -Wl,-z,noexecstack` 与显式 `--without-gnutls`，新增 `INSTALL_TEST_RUNNERS` 并跳过 MIPS 无用 `qemu-user`；`test.sh` 增加 ELF NX 堆栈断言；维护工作流锁定 Action SHA 并为清空历史增加 `CLEAR-HISTORY` 确认 | Shell/Python/YAML 静态校验通过；待 CI 构建验证 |
| 统一源码、依赖完整性与 libssh2 安全快照 | [abcfy2](https://github.com/abcfy2/aria2-static-build/tree/a9e4ba3)、[DoTheBetter](https://github.com/DoTheBetter/aria2_build/tree/47cf3a9)、[libssh2 397ac69](https://github.com/libssh2/libssh2/commit/397ac69b694176cf23aff5a53dc956223cd581ab) | 11 项依赖全部锁定 SHA-256（截至 2026-11 仅 OpenSSL 3.5.9 待升级 `3.5.10`，其余 10 项均为最新稳定/安全快照） | 已验证（归档与依赖校验） |

## 候选功能与社区方案对比（含 Round-2 新挖掘）

| 候选 | 来源与许可 | 解决的问题与实现差异 | 改进价值 | 整合状态与说明 |
|---|---|---|---|---|
| **CVE-2026-75421（`IOFile::getLine` 栈下溢）** | [Issue #2375](https://github.com/aria2/aria2/issues/2375) / [PR #2376](https://github.com/aria2/aria2/pulls) / [openSUSE RPM](https://www.rpmfind.net/linux/RPM/opensuse/tumbleweed/x86_64/aria2-1.37.0-3.2.x86_64.html)（GPL-2.0-or-later） | 输入文件/会话/Cookie 行首为 `\0` 时 `strlen(buf)==0` 导致 `buf[-1]` 栈下溢 | **高（P0 安全）** | 待拉取上游源码后精确生成补丁并加 CppUnit（离线沙箱无法核对 `IOFile.cc` 精确行上下文，拒绝猜测） |
| **CVE-2026-8367（TLS 服务端 EKU 缺失）** | [Tenable TRA-2026-38](https://www.tenable.com/security/research/tra-2026-38) / [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-8367)（独立实现） | 客户端未校验服务端证书 `serverAuth` EKU，接受 `clientAuth` 证书；需在 `LibsslTLSContext.cc` 设置 `X509_PURPOSE_SSL_SERVER` | **高（P0 安全）** | 待拉取上游源码后实现并配套 TLS 回环测试 |
| **`Content-Disposition` 尾随分号兼容** | [Issue #1118](https://github.com/aria2/aria2/issues/1118) / PR #2153（GPL-2.0-or-later） | AWS S3/CloudFront、HuggingFace、nginx 返回末尾带 `;` 的头导致文件名退化为 `index.html`/ETag | **高（P1 兼容）** | 待拉取上游 `src/util.cc` 后精确落地并补回环测试 |
| **Y2038 溢出、`parseUIntNoThrow` 上界与 MinGW `SIZE_MAX`** | [PR #2354](https://github.com/aria2/aria2/pulls)、[PR #2349](https://github.com/aria2/aria2/pulls)、[PR #2348](https://github.com/aria2/aria2/pulls)（GPL-2.0-or-later） | 修复 32 位目标 2038 时间溢出、无符号解析上界错误及现代 MinGW 宏冲突 | **中高（P1 正确性）** | 待拉取上游源码后核对 diff 并整合 |
| **OpenSSL 3.x 版本号显示与 OpenSSL 4 适配** | `docs/distribution.md`、[PR #2403](https://github.com/aria2/aria2/pulls) | 修复 `aria2c --version` 将 `3.5.9` 显示为 `3.5.0i`；未来升级 OpenSSL 4.x 时引入 PR #2403 | **中（P1/P2）** | 待拉取 `FeatureConfig.cc` 源码后修复 3.x 显示；4.x 暂观望（当前锁定 3.5 LTS） |
| **macOS 静态 OpenSSL 替代 AppleTLS 动态构建** | [Issue #2277](https://github.com/aria2/aria2/issues/2277)（AppleTLS TLS 1.3 失败） | 当前 macOS 产物动态依赖 7 个 Homebrew `.dylib` 且 AppleTLS 不支持部分 TLS 1.3 站点 | **高（破坏性变更）** | **需用户确认**：切换 TLS 后端与静态依赖构建将改变产物形态 |
| **Windows OpenSSL CA 证书开箱可用性** | [asdo92](https://github.com/asdo92/aria2-static-builds)、[Issue #1801](https://github.com/aria2/aria2/issues/1801) | 当前 Windows OpenSSL 构建指向 `/etc/ssl`，无默认 CA 证书；可选随包附带 `cacert.pem` 或切回 WinTLS | **高（破坏性变更）** | **需用户确认**：涉及分发文件变更或 TLS 后端切换 |
| **CLI `-i -` 管道阻塞 / BT `--remove-control-file` / PT `private` 显示** | [PR #2363](https://github.com/aria2/aria2/pulls)、[PR #2336](https://github.com/aria2/aria2/pulls)、[PR #2367](https://github.com/aria2/aria2/pulls) | 改善自动化管道输入、BT 控制文件清理及 PT 种子 `private` 标记可见性 | **中（P2 体验）** | 待核对具体 diff 后按需整合 |
| **原生 SOCKS5 / SOCKS5h 代理** | [PR #2360](https://github.com/aria2/aria2/pulls)、[Issue #153](https://github.com/aria2/aria2/issues/153) | 为 HTTP/HTTPS/FTP/SFTP 增加 `socks5://`/`socks5h://` 及认证 | **中（改动面大）** | 需独立 SOCKS5 回环测试套件验证后再评估 |
| **Windows ARM64（`aarch64-w64-mingw32`）** | [mstorsjo/llvm-mingw](https://github.com/mstorsjo/llvm-mingw)、[Motrix #25](https://github.com/motrixapp/aria2/pull/25)、[minnyres](https://github.com/minnyres/aria2-windows-arm64/tree/08e701b09516558c8c5ef4ce314936f14e2f3575) | 基于 LLVM-MinGW UCRT 新增 Windows ARM64 静态构建 | **中（P2 平台）** | 需额外验证 autotools/libtool 与 LLD 链接兼容性 |
| **连接数/分片进一步放宽** | [Cabbage](https://github.com/Cabbagec/aria2-enhanced/tree/01512fc1)、[hguandl](https://github.com/hguandl/aria2-patch/tree/2fd5c3a)、[hosxy](https://github.com/hosxy/aria2-fast) | 现有 `0002` 已解除上限并保留合理默认值 16 | 低（已覆盖） | 维持现状 |
| **BT tracker 全轮询 / 反吸血 / HTTP2 模拟 / aria2-next 重写** | [qydysky](https://github.com/qydysky/aria2_patch/tree/0feb0126117d334d6038bb3dc10402b4541f3669)、[aria2b](https://github.com/makeding/aria2b/tree/3eed57f)、[上游 #2157](https://github.com/aria2/aria2/pull/2157)、[上游 #2409](https://github.com/aria2/aria2/pull/2409)、[aria2-next](https://github.com/AnInsomniacy/aria2-next/tree/1b8fb72fc) | 反吸血与非标轮询破坏正常 peer/announce 语义；`aria2-next` 破坏 `.aria2`/libaria2 兼容；`#2157` 可待独立 tracker 测试后评估 | 低–中（高风险） | 暂不引入破坏协议/兼容性的方案 |

## 复现验证

```bash
./scripts/test.sh /path/to/patched/aria2c --target x86_64-unknown-linux-gnu --lite --require-static
./scripts/test.sh /path/to/vanilla/aria2c --target x86_64-unknown-linux-gnu --lite --require-static --patch-mode vanilla
python3 scripts/benchmark-http.py /path/to/vanilla/aria2c /path/to/previous/aria2c /path/to/patched/aria2c
```

## 历史本机基准结果（Round-1，2026-11-19 Linux x86_64）

上游提交、编译配置与直接链接依赖相同。每轮下载 12 MiB 固定负载，服务端每 64 KiB 间隔 4 ms，预热一轮后测量五轮，均通过 SHA-256 校验：

| 构建 | 单连接中位耗时 / 吞吐 | 四连接中位耗时 / 吞吐 | 四连接进程 CPU 中位值 |
|---|---:|---:|---:|
| 上游原版 | 0.791 s / 15.17 MiB/s | 0.216 s / 55.63 MiB/s | 30.0 ms |
| 原有六个补丁 | 0.807 s / 14.86 MiB/s | 0.213 s / 56.28 MiB/s | 27.5 ms |
| Round-1 增强版 | 0.789 s / 15.21 MiB/s | 0.217 s / 55.26 MiB/s | 31.9 ms |

> Round-2 新增的 `0004`/`0006` 修复与 `0017`（Nettle 4.0）不改变 HTTP 传输热路径，但因离线沙箱无外网拉取上游源码与工具链镜像，Round-2 变更的实际编译与运行时基准测试需在 GitHub Actions CI 流水线中执行确认。
