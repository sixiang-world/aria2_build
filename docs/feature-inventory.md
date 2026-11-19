# Aria2 功能对照与验证

默认源码为上游 `9e7273583f83e881e3ec067b523ba88724088d2f`（截至 2026-11-19 上游 `master` 无更新提交）。`patched` 和 `vanilla` 使用同一来源；对照时分别应用或跳过完整补丁队列。

## 已整合（`patch/aria2-0001` – `0023` 与构建工程）

| 功能 | 来源 | 实现 | 验证状态 |
|---|---|---|---|
| 连接上限、分片、并发和续传默认值 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch)、[上游 #1431](https://github.com/aria2/aria2/pull/1431) | 保留 `0002`；`test.sh` 通过 `--help` 与 `--help=#http` 全量断言 7 项调优默认值 | 已验证（20 路 Range 并发、SHA-256 及续传） |
| 慢速、断连恢复 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch) | 保留 `0003`，复用原有重试与分片机制 | 已验证（回环限速与中断恢复） |
| 4xx 重试与服务端退避 | 现有 `0005`、[RFC 9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after) | `0008` 让专用开关优先，429/503 遵守 `Retry-After`（上限 600s）；`0015` 修正等待中请求被重复计入连接数 | 已验证（回环与 CppUnit） |
| 裸 DEFLATE | [Elypha 0007](https://github.com/Elypha/aria2-mod/blob/941a5db1c7f3e6e26249aeceedbf7023a8d0aa36/aria2-patch/0007-retry-raw-deflate-mode.patch)、[上游 #2268](https://github.com/aria2/aria2/pull/2268) | `0007` 在写入前识别封装或裸流，保持校验错误为失败 | 已验证（7 项回环解压用例） |
| 分块 206 续传 | [Motrix d5e6f8ae](https://github.com/motrixapp/aria2/commit/d5e6f8aee6de4d03e94aec9af3b3efac5aff06bc)、[上游 #1115](https://github.com/aria2/aria2/issues/1115) | `0012` + `0016` 保留合法 `Content-Range`，校验起点、范围与总长度 | 已验证（回环正/负用例） |
| 备用 IP 连接 | [Motrix #33](https://github.com/motrixapp/aria2/pull/33) | `0013` 在连接错误或 Winsock `exceptfds` 异常通知后切换备用地址，修正备用 IPv4 超时分支 | 已验证（CppUnit 本地套接字；Windows 实机待验） |
| BT 顺序请求 | [上游 #1671](https://github.com/aria2/aria2/pull/1671) | `0010` 增加可选 `--bt-piece-selector=inorder`，保留默认随机策略与显式优先项 | 已验证（回环 tracker/peer 与 endgame） |
| BT metainfo 与 piece 校验 | [上游 #2401](https://github.com/aria2/aria2/pull/2401)、[上游 #2372](https://github.com/aria2/aria2/pull/2372)（CVE-2026-71832）、[Motrix #28](https://github.com/motrixapp/aria2/pull/28) | `0009`（`dynamic_cast` 保护）+ `0011`（piece 长度与哈希对齐无溢出校验） | 已验证（静态编译、BT 回环与 CppUnit） |
| 本地配置、MinGW daemon 及 Windows 信息（Round-2 修复） | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087) + Round-2 审查修复 | `0001` 保留；`0004` 修复 `CreateProcessW` 不可写缓冲区 UB、补齐 `si.cb`/`SW_HIDE` 与 `GetLastError()` 诊断；`0006` 修复 `szCSDVersion` 宽字符指针输出 Bug 并新增 Windows 11 及 Server 2019/2022/2025 识别 | 补丁上下文已校验；待 MinGW CI 编译验证 |
| Nettle 4.0 编译兼容（`0017`） | [上游 PR #2358](https://github.com/aria2/aria2/pulls) / [openSUSE Factory](https://build.opensuse.org/projects/openSUSE:Factory/packages/aria2/files/aria2-Fix-build-with-nette4.patch?expand=0)（GPL-2.0-or-later） | `0017` 按 `NETTLE_VERSION_MAJOR > 3` 适配 `hash->digest` 新签名 | 审计员实测可依序应用至锁定提交；待 CI 编译验证 |
| **CVE-2026-75421 `IOFile::getLine` 栈下溢修复（`0018`）** | [上游 PR #2376](https://github.com/aria2/aria2/pull/2376/files) / [Issue #2375](https://github.com/aria2/aria2/issues/2375)（GPL-2.0-or-later） | `0018` 在访问 `buf[len - 1]` 前增加 `len > 0` 守卫；`test-http-reliability.py` 新增前导 `\0` 输入文件回归用例 | 精确上游 diff 已校验；待 CI 编译与回归验证 |
| **`Content-Disposition` 尾随分号兼容（`0019`）** | [Issue #1118](https://github.com/aria2/aria2/issues/1118) / [PR #2153](https://github.com/aria2/aria2/pull/2153/files)（独立修正） | `0019` 在解析前剔除尾随 `;`，同时修正 PR #2153 中 `*eop` 越界解引用 Bug（改为 `while (p != eop && *(eop - 1) == ';') --eop;`）；`test-http-reliability.py` 新增回环回归用例 | 精确上游上下文已校验；待 CI 编译与回归验证 |
| **ServerStatMan Y2038 溢出修复（`0020`）** | [上游 PR #2354](https://github.com/aria2/aria2/pull/2354/files)（GPL-2.0-or-later） | `0020` 将 `S_LAST_UPDATED` 解析由 `int32_t` + `parseIntNoThrow` 升级为 `int64_t` + `parseLLIntNoThrow` | 精确上游 diff 已校验；待 CI 编译验证 |
| **Windows `longPathAware` 清单与 Mozilla `cacert.pem`** | [Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)、[curl CA Extract](https://curl.se/docs/caextract.html)（MPL-2.0） | `build.sh` 通过 `windres` 嵌入 `build-aux/aria2c.exe.manifest`（免改上游源码），并随 Windows ZIP 打包 SHA-256 锁定的 `cacert-2026-11-05.pem` | 脚本与配置静态校验通过；待 MinGW CI 验证 |
| **macOS `arm64` 自包含静态依赖 + OpenSSL 构建** | [Issue #2277](https://github.com/aria2/aria2/issues/2277)、[OpenSSL 3.5](https://openssl-library.org/source/) | `full.yml` 改为从 `dependencies.tsv` 静态编译全部依赖并链接 OpenSSL（`--with-ca-bundle=/etc/ssl/cert.pem`），强制 `otool -L` 非系统库零泄漏门禁与 ad-hoc `codesign` | YAML/Shell 校验通过；待 `macos-15` CI 验证 |
| **MinGW `#undef SIZE_MAX` 清理（`0021`）** | [上游 PR #2348](https://github.com/aria2/aria2/pull/2348/files)（GPL-2.0-or-later） | `0021` 移除 `gai_strerror.h`/`getaddrinfo.h`/`gettimeofday.h` 中过时的 `#undef SIZE_MAX` | 精确上游 diff 已校验；待 MinGW CI 验证 |
| **BT `--remove-control-file` 修复（`0022`）** | [上游 PR #2336](https://github.com/aria2/aria2/pull/2336/files)（GPL-2.0-or-later） | `0022` 在 `src/RequestGroup.cc` 正确响应 BT 任务的 `--remove-control-file` | 精确上游 diff 已校验（已对齐 `0010` 行偏移）；待 CI 验证 |
| **PT 种子 `Private` 标志显示（`0023`）** | [上游 PR #2367](https://github.com/aria2/aria2/pull/2367/files)（GPL-2.0-or-later） | `0023` 在 `aria2c -S`/`--show-files` 中输出 `Private: yes/no` | 精确上游 diff 已校验；待 CI 验证 |
| **本地 HTTPS 证书回环测试与依赖自动巡检** | 本仓库 | 新增 `scripts/test-http-tls.py`（自签名 CA 放行 + 未信证书拒绝）接入 `test.sh`；新增 `scripts/check-dependencies.py` 与 `.github/workflows/check-dependencies.yml` | Python/YAML/SHA 校验通过；待 CI 运行验证 |

## 候选功能与社区方案对比（剩余待评估项）

| 候选 | 来源与许可 | 解决的问题与实现差异 | 改进价值 | 当前状态 |
|---|---|---|---|---|
| **CVE-2026-8367（TLS 服务端 EKU 缺失）** | [Tenable TRA-2026-38](https://www.tenable.com/security/research/tra-2026-38) / [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-8367) | 客户端未校验 `serverAuth` EKU；需在 `LibsslTLSContext.cc` 设置 `X509_PURPOSE_SSL_SERVER` | **高（P0）** | 需拉取上游 `LibsslTLSContext.cc` 精确源码后落地 |
| **`parseUIntNoThrow` 上界（PR #2349）** | [PR #2349](https://github.com/aria2/aria2/pull/2349/files) | 改为 `unsigned long` + `strtoul`；但需先核实 `parseLong` 在 Windows LLP64（32 位 `unsigned long`）下是否拒绝负数字符串 `"-1"` | **中（P1）** | 审慎暂缓，待核实 `parseLong` 源码后再合入 |
| **Linux musl `-static-pie` ASLR** | [Static PIE with musl](https://gaultier.github.io/blog/build-pie-executables-with-pie.html) | `ARIA2_STATIC=yes` 通过 libtool 注入 `-all-static` 会与 `-static-pie` 冲突，且依赖容器 sysroot 的 `rcrt1.o` 与 `-fPIC` `libstdc++.a` | **中（P2）** | 待在 `abcfy2` 容器内实测后再启用 |
| **Windows ARM64（`aarch64-w64-mingw32`）** | [mstorsjo/llvm-mingw](https://github.com/mstorsjo/llvm-mingw)、[Motrix #25](https://github.com/motrixapp/aria2/pull/25) | 基于 LLVM-MinGW UCRT 交叉编译 | **中（P2）** | 待验证 libtool 与 LLD 链接兼容性 |
| **原生 SOCKS5 / `-i -` 管道非阻塞** | [PR #2360](https://github.com/aria2/aria2/pulls)、[PR #2363](https://github.com/aria2/aria2/pull/2363/files) | 扩展原生 SOCKS5 代理与 `-i -` 管道流式输入（PR #2363 抓取 diff 在 `download_helper.cc` 存在括号语法瑕疵，待本地源码核对） | **中（P2）** | 待拉取上游源码核对并配回归测试后合入 |

## 历史本机基准结果（Round-1，2026-11-19 Linux x86_64）

| 构建 | 单连接中位耗时 / 吞吐 | 四连接中位耗时 / 吞吐 | 四连接进程 CPU 中位值 |
|---|---:|---:|---:|
| 上游原版 | 0.791 s / 15.17 MiB/s | 0.216 s / 55.63 MiB/s | 30.0 ms |
| 原有六个补丁 | 0.807 s / 14.86 MiB/s | 0.213 s / 56.28 MiB/s | 27.5 ms |
| Round-1 增强版 | 0.789 s / 15.21 MiB/s | 0.217 s / 55.26 MiB/s | 31.9 ms |
