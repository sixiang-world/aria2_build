# TODO

> 跟踪本仓库尚未完成 / 待改进的事项。已完成项归档到文件末尾的「已完成」小节。

## 待办（按优先级）

### P0 — 安全漏洞修复（需在拉取上游 `aria2` 源码树后生成精确上下文补丁并编译验证）

- [ ] **CVE-2026-75421（`IOFile::getLine()` 栈下溢）**：回移上游 [PR #2376](https://github.com/aria2/aria2/pulls) / [Issue #2375](https://github.com/aria2/aria2/issues/2375)（openSUSE Tumbleweed 已合入 `aria2-Fix-stack-buffer-underflow-in-IOFile-getLine.patch`），防止含前导 `\0` 的输入文件/会话/Cookie 文件触发 `buf[-1]` 越界读，并补充 CppUnit 回归测试。
- [ ] **CVE-2026-8367（缺失 TLS 服务端证书 EKU 校验）**：针对 [Tenable TRA-2026-38](https://www.tenable.com/security/research/tra-2026-38)，在 `src/LibsslTLSContext.cc` 客户端上下文显式强制 `X509_PURPOSE_SSL_SERVER`（`X509_VERIFY_PARAM_set_purpose`），并增加本地 TLS 回环测试（拒绝仅含 `clientAuth` EKU 的证书）。

### P1 — 高价值协议兼容性、正确性与依赖升级

- [ ] **HTTP `Content-Disposition` 尾随分号兼容（[Issue #1118](https://github.com/aria2/aria2/issues/1118) / PR #2153）**：修复 AWS S3/CloudFront、HuggingFace、nginx 返回末尾带 `;` 的 `Content-Disposition` 时被拒收导致文件名退化为 `index.html`/ETag 的问题（修改 `src/util.cc` `parse_content_disposition` 并补回环测试）。
- [ ] **核心工具与 32 位正确性**：回移上游 [PR #2354](https://github.com/aria2/aria2/pulls)（Y2038 整数溢出，保护 32 位 Linux/Windows/MIPS 目标）、[PR #2349](https://github.com/aria2/aria2/pulls)（`util::parseUIntNoThrow` 上界修复）与 [PR #2348](https://github.com/aria2/aria2/pulls)（移除 MinGW 过时 `#undef SIZE_MAX`）。
- [ ] **OpenSSL 3.5.10 依赖升级**：待上游发布 OpenSSL `3.5.10` 后更新 `build-aux/dependencies.tsv` 及 SHA-256，清零 2026-11 披露的 8 个 Low CVE。
- [ ] **OpenSSL 3.x 版本号显示修复**：修复 `src/FeatureConfig.cc` 沿用 OpenSSL 1.x 位移解析导致 `aria2c --version` 将 `3.5.9` 显示为 `3.5.0i` 的问题。

### P2 — 架构决策（涉及行为变更，待确认后实施）与跨平台扩展

- [ ] **Windows OpenSSL CA 证书开箱可用性**：当前 Windows Full 构建采用 `--without-wintls --with-openssl` 且 `--openssldir=/etc/ssl`，无默认 CA 证书库。需决策：随 ZIP 附带 Mozilla `cacert.pem`（并设置默认查找路径），或切回 WinTLS（Schannel）。
- [ ] **macOS `arm64` 便携化与 TLS 1.3 修复**：当前 `full.yml` 使用 `--with-appletls`（[Issue #2277](https://github.com/aria2/aria2/issues/2277) 存在 TLS 1.3 握手失败）且动态链接 Homebrew `.dylib`。需决策：改为从源码静态编译依赖 + OpenSSL 生成真正单文件 `aria2c` 并加 `codesign` 与 `otool -L` 门禁。
- [ ] **CLI / BitTorrent / 代理增强评估**：按需评估并验证 [PR #2363](https://github.com/aria2/aria2/pulls)（`-i -` 管道阻塞）、[PR #2336](https://github.com/aria2/aria2/pulls)（BT `--remove-control-file`）、[PR #2367](https://github.com/aria2/aria2/pulls)（`--show-files` 显示 `private` 标志）、[PR #2157](https://github.com/aria2/aria2/pull/2157)（同层 Tracker 轮换）及 [PR #2360](https://github.com/aria2/aria2/pulls)（原生 SOCKS5 代理）。
- [ ] **Windows ARM64（`aarch64-w64-mingw32`）**：基于 `mstorsjo/llvm-mingw`（UCRT）验证交叉编译流水线接入。

---

## 已完成

- [x] 2026-06 整理 `temp/*.md` → `docs/build-system-design.md` + `docs/TODO.md` + `docs/code-review.md`
- [x] 2026-06 仓库清理：建立 `.gitignore`，移除 `temp/`，去重 workflow，统一补丁目录
- [x] 2026-10 新增自动化测试流水线 `scripts/test.sh`，`full.yml` 和 `lite.yml` 均内置测试与 `verify-artifacts` 门禁
- [x] 2026-10 上游同步与 MIPS 平台恢复
- [x] 2026-11 Round-1 增强补丁 `0007`–`0016`、`build-aux/` 依赖与工具链锁定、本地回环 HTTP/压缩/BT 测试与基准测试
- [x] 2026-11 Round-2 深度审查与升级：修复补丁 `0004` Win32 UB 与 `0006` 宽字符指针 Bug / Win11 & Server 2019–2025 识别；新增补丁 `0017`（Nettle 4.0 兼容）；加固 `build.sh` 安全编译/链接选项与 MIPS/本地构建体验；加固维护工作流（锁定 SHA + `CLEAR-HISTORY` 确认）；补齐 `test.sh` 默认值与 NX 检查；修复 `README.md` 坏链并同步文档
