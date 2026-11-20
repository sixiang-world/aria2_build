# Aria2 功能对照与验证

默认源码读取 `build-aux/aria2.commit`。`patched` 和 `vanilla` 使用同一来源，分别应用补丁队列或使用纯净源码。Full 的 `exclude_patches` 可按编号跳过队列中的指定补丁。

## 当前补丁队列（`0001`–`0027`）与构建工程

| 功能 | 来源 | 实现 | 验证状态 |
|---|---|---|---|
| 连接上限、分片、并发和续传默认值 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch)、[上游 #1431](https://github.com/aria2/aria2/pull/1431) | 保留 `0002`；`test.sh` 通过 `--help` 与 `--help=#http` 断言调优默认值 | 回环覆盖 20 路 Range 并发、SHA-256 及续传 |
| 慢速、断连恢复 | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087)、[P3TERX](https://github.com/P3TERX/Aria2-Pro-Core/tree/4542bf8/patch) | 保留 `0003`，复用原有重试与分片机制 | 已验证（回环限速与中断恢复） |
| 4xx 重试与服务端退避 | 现有 `0005`、[RFC 9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after) | `0008` 让专用开关优先，429/503 遵守 `Retry-After`（上限 600s）；`0015` 修正等待中请求被重复计入连接数 | 已验证（回环与 CppUnit） |
| HTTP 续传验证（`0026`） | [RFC 9110 If-Range](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-range) | `.aria2` 保留版本及进度字段并增加可选验证器。对匹配资源发送 `If-Range`，收到完整响应时先保存重置后的进度，再重下 | 回环与 CppUnit 覆盖新旧控制文件及续传响应 |
| 同源连接预算与共享冷却（`0027`） | 本仓库 | `--max-overall-connection-per-origin=16`，`0` 关闭连接预算。带有效 `Retry-After` 的 `429` 或 `503` 更新主机冷却时间 | 回环与 CppUnit 覆盖并发、任务轮转及冷却 |
| 裸 DEFLATE | [Elypha 0007](https://github.com/Elypha/aria2-mod/blob/941a5db1c7f3e6e26249aeceedbf7023a8d0aa36/aria2-patch/0007-retry-raw-deflate-mode.patch)、[上游 #2268](https://github.com/aria2/aria2/pull/2268) | `0007` 在写入前识别封装或裸流，保持校验错误为失败 | 已验证（7 项回环解压用例） |
| 分块 206 续传 | [Motrix d5e6f8ae](https://github.com/motrixapp/aria2/commit/d5e6f8aee6de4d03e94aec9af3b3efac5aff06bc)、[上游 #1115](https://github.com/aria2/aria2/issues/1115) | `0012` + `0016` 保留合法 `Content-Range`，校验起点、范围与总长度 | 已验证（回环正/负用例） |
| 备用 IP 连接 | [Motrix #33](https://github.com/motrixapp/aria2/pull/33) | `0013` 在连接错误或 Winsock `exceptfds` 异常通知后切换备用地址，修正备用 IPv4 超时分支 | 已验证（CppUnit 本地套接字；Windows 实机待验） |
| BT 顺序请求 | [上游 #1671](https://github.com/aria2/aria2/pull/1671) | `0010` 增加可选 `--bt-piece-selector=inorder`，保留默认随机策略与显式优先项 | 已验证（回环 tracker/peer 与 endgame） |
| BT metainfo 与 piece 校验 | [上游 #2401](https://github.com/aria2/aria2/pull/2401)、[上游 #2372](https://github.com/aria2/aria2/pull/2372)（CVE-2026-71832）、[Motrix #28](https://github.com/motrixapp/aria2/pull/28) | `0009`（`dynamic_cast` 保护）+ `0011`（piece 长度与哈希对齐无溢出校验） | 已验证（静态编译、BT 回环与 CppUnit） |
| 本地配置、MinGW daemon 及 Windows 信息（Round-2 修复） | [myfreeer](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087) + Round-2 审查修复 | `0001` 保留；`0004` 修复 `CreateProcessW` 不可写缓冲区 UB、补齐 `si.cb`/`SW_HIDE` 与 `GetLastError()` 诊断；`0006` 修复 `szCSDVersion` 宽字符指针输出 Bug 并新增 Windows 11 及 Server 2019/2022/2025 识别 | 补丁上下文已校验；待 MinGW CI 编译验证 |
| Nettle 4.0 编译兼容（`0017`） | [上游 PR #2358](https://github.com/aria2/aria2/pulls) / [openSUSE Factory](https://build.opensuse.org/projects/openSUSE:Factory/packages/aria2/files/aria2-Fix-build-with-nette4.patch?expand=0)（GPL-2.0-or-later） | `0017` 按 `NETTLE_VERSION_MAJOR > 3` 适配 `hash->digest` 新签名 | 审计员实测可依序应用至锁定提交；待 CI 编译验证 |
| **CVE-2026-75421 `IOFile::getLine` 栈下溢修复（`0018`）** | [上游 PR #2376](https://github.com/aria2/aria2/pull/2376/files) / [Issue #2375](https://github.com/aria2/aria2/issues/2375)（GPL-2.0-or-later） | `0018` 在访问 `buf[len - 1]` 前增加 `len > 0` 守卫；`test-http-reliability.py` 新增前导 `\0` 输入文件回归用例 | 精确上游 diff 已校验；待 CI 编译与回归验证 |
| **`Content-Disposition` 尾随分号兼容（`0019`）** | [Issue #1118](https://github.com/aria2/aria2/issues/1118) / [PR #2153](https://github.com/aria2/aria2/pull/2153/files)（独立实现） | 在半开区间内处理尾随分号。上游 CppUnit 的相关断言随解析约定更新，另有 HTTP 回环用例校验下载文件名和内容 | 待更新后的 CppUnit 与回环 CI 验证 |
| **ServerStatMan Y2038 溢出修复（`0020`）** | [上游 PR #2354](https://github.com/aria2/aria2/pull/2354/files)（GPL-2.0-or-later） | `0020` 将 `S_LAST_UPDATED` 解析由 `int32_t` + `parseIntNoThrow` 升级为 `int64_t` + `parseLLIntNoThrow` | 精确上游 diff 已校验；待 CI 编译验证 |
| **Windows `longPathAware` 清单与 Mozilla `cacert.pem`** | [Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)、[curl CA Extract](https://curl.se/docs/caextract.html)（MPL-2.0） | `build.sh` 通过 `windres` 嵌入 Windows 清单，长路径还需要系统启用 `LongPathsEnabled`。补丁 `0023` 通过 `GetModuleFileNameW` 找到 exe 路径。Windows OpenSSL 按显式 CA、`SSL_CERT_FILE`、同目录 `cacert.pem`、OpenSSL 默认路径加载证书 | Windows CI 验证、原生长路径和系统信任库待确认 |
| **OpenSSL 3.x 版本显示（`0024`）** | 本仓库 | `FeatureConfig.cc` 从 OpenSSL 3.x 读取运行库的完整版本号，保留 1.x 和 LibreSSL 的版本格式化路径 | Linux 版本验证见下方 |
| **WinTLS 服务端证书校验（`0025`）** | 本仓库 | 在 Schannel 握手后使用系统信任库核验完整链、`serverAuth` 用途及主机名，IP 地址匹配证书 SAN | Wine 10 实测锁定上游 WinTLS 接受未受信任证书，详见本轮验证 |
| **macOS `arm64` 构建** | `full.yml` 的 macOS 构建任务、[AppleTLS 兼容性报告 #2277](https://github.com/aria2/aria2/issues/2277) | 保留 AppleTLS 和 Homebrew 动态链接，产物名含 `macos-dynamic`。Homebrew 包版本及 `otool -L` 链接信息写入 `build_info.md` | 待当前补丁队列在 `macos-15` 上的验证 |
| **MinGW `#undef SIZE_MAX` 清理（`0021`）** | [上游 PR #2348](https://github.com/aria2/aria2/pull/2348/files)（GPL-2.0-or-later） | `0021` 移除 `gai_strerror.h`/`getaddrinfo.h`/`gettimeofday.h` 中过时的 `#undef SIZE_MAX` | 精确上游 diff 已校验；待 MinGW CI 验证 |
| **BT 种子 `Private` 标志显示（`0022`）** | [上游 PR #2367](https://github.com/aria2/aria2/pull/2367/files)（GPL-2.0-or-later） | `aria2c -S` / `--show-files` 输出 `Private: yes/no`，只读取并显示已有属性 | 待 CI 验证 |
| **本地 HTTPS 证书回环测试** | 本仓库 | 验证受信 CA 成功、未知 CA 拒绝、主机名不匹配拒绝，以及仅含 `clientAuth` EKU 的叶子证书拒绝。WinTLS 使用系统证书库，跳过需要 `--ca-certificate` 的用例 | Linux 回环结果见下方，Windows CI 待确认 |
| **Full 自定义构建** | 本仓库 | 支持 OpenSSL、LibreSSL 和 Windows WinTLS（libssh2 使用 WinCNG，`--version` 标明 WinTLS），以及补丁排除、额外 configure 参数和优化级别。关闭 `run_tests` 只产出构建资产 | 本地选项与 WinTLS 交叉构建结果见下方，Windows CI 待确认 |
| **上游同步和发版** | 本仓库 | 每日或手动比较上游提交和正式标签。共用补丁源码归档，Lite CppUnit 和 Full 通过测试与产物门禁后写回并发布。失败时创建或更新 Issue | GitHub Actions 的分支写入、发布标签及 Issue 权限待仓库端验证 |

## 候选功能与社区方案对比（剩余待评估项）

| 候选 | 来源与许可 | 解决的问题与实现差异 | 改进价值 | 当前状态 |
|---|---|---|---|---|
| **BT `--remove-control-file`** | [上游 PR #2336](https://github.com/aria2/aria2/pull/2336/files) | 独立验证清除进度文件、现有目标文件保护及分片校验之间的关系 | 避免误用 BT 恢复状态 | 从当前补丁队列移除，待独立评估 |
| **CVE-2026-8367（TLS 服务端 EKU 报告）** | [Tenable TRA-2026-38](https://www.tenable.com/security/research/tra-2026-38) / [NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-8367) | 回环测试用相同可信 CA 签发 `serverAuth` 和仅含 `clientAuth` 的证书，验证服务器证书用途检查 | 证书用途回归覆盖 | Linux OpenSSL 和 Wine 下的 WinTLS 均拒绝仅含 `clientAuth` 的证书。原生 Windows 系统信任库待 CI 验证 |
| **`parseUIntNoThrow` 上界（PR #2349）** | [PR #2349](https://github.com/aria2/aria2/pull/2349/files) | 改为 `unsigned long` + `strtoul`；但需先核实 `parseLong` 在 Windows LLP64（32 位 `unsigned long`）下是否拒绝负数字符串 `"-1"` | **中（P1）** | 审慎暂缓，待核实 `parseLong` 源码后再合入 |
| **Linux musl `-static-pie` ASLR** | [Static PIE with musl](https://gaultier.github.io/blog/build-pie-executables-with-pie.html) | `ARIA2_STATIC=yes` 通过 libtool 注入 `-all-static` 会与 `-static-pie` 冲突，且依赖容器 sysroot 的 `rcrt1.o` 与 `-fPIC` `libstdc++.a` | **中（P2）** | 待在 `abcfy2` 容器内实测后再启用 |
| **Windows ARM64（`aarch64-w64-mingw32`）** | [mstorsjo/llvm-mingw](https://github.com/mstorsjo/llvm-mingw)、[Motrix #25](https://github.com/motrixapp/aria2/pull/25) | 基于 LLVM-MinGW UCRT 交叉编译 | **中（P2）** | 待验证 libtool 与 LLD 链接兼容性 |
| **原生 SOCKS5 / `-i -` 管道非阻塞** | [PR #2360](https://github.com/aria2/aria2/pulls)、[PR #2363](https://github.com/aria2/aria2/pull/2363/files) | 扩展原生 SOCKS5 代理与 `-i -` 管道流式输入（PR #2363 抓取 diff 在 `download_helper.cc` 存在括号语法瑕疵，待本地源码核对） | **中（P2）** | 待拉取上游源码核对并配回归测试后合入 |

## 本轮本地验证

- 在 `build-aux/aria2.commit` 锁定的源码上依序应用 25 个补丁。`EXCLUDE_PATCHES=0001,0022` 仅跳过指定两项，错误格式会被拒绝。
- Linux x86_64 静态构建链接锁定的 OpenSSL 3.5.9，`aria2c --version` 显示 `OpenSSL/3.5.9`。`make -j3 check` 的 CppUnit 套件通过 930 项。`scripts/test.sh /path/to/aria2c --lite --require-static` 通过 16 项门禁，包括公网 HTTPS、本地错误主机名拒绝和 `clientAuth`-only EKU 拒绝。
- 锁定 MinGW 容器以 `compiler_opt=-Os` 和 `run_tests=false` 交叉编译 Windows x86_64 WinTLS/WinCNG。产物打包为 `*_static_wintls.zip`，内含二进制和许可文件。另用 Wine 运行 `scripts/test.sh`，13 项通过、1 项公网探测因环境证书根未受信而跳过、0 项失败。完整二进制在隔离 Wine 证书库中实测接受可信的 `serverAuth` 证书，并拒绝仅含 `clientAuth` 的证书和错误 IP SAN。
- 使用构建替身核对了 Linux 的 WinTLS → OpenSSL 回退、额外参数的引号保留、优化级别和测试开关。工作流检查验证 `run_tests=false` 会跳过发布。本地 Git 与 API 模拟覆盖同步成功、发布失败回滚和分支租约冲突。

## 历史本机基准结果（Round-1，2026-11-19 Linux x86_64）

| 构建 | 单连接中位耗时 / 吞吐 | 四连接中位耗时 / 吞吐 | 四连接进程 CPU 中位值 |
|---|---:|---:|---:|
| 上游原版 | 0.791 s / 15.17 MiB/s | 0.216 s / 55.63 MiB/s | 30.0 ms |
| 原有六个补丁 | 0.807 s / 14.86 MiB/s | 0.213 s / 56.28 MiB/s | 27.5 ms |
| Round-1 增强版 | 0.789 s / 15.21 MiB/s | 0.217 s / 55.26 MiB/s | 31.9 ms |
