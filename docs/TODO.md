# TODO

> 跟踪本仓库尚未完成 / 待改进的事项。已完成项归档到文件末尾的「已完成」小节。

## 待办（按优先级）

### P0 — 安全修复（需拉取上游完整源码后编写精确上下文补丁与 CppUnit/TLS 测试）

- [ ] **CVE-2026-8367（缺失 TLS 服务端证书 EKU 校验）**：针对 [Tenable TRA-2026-38](https://www.tenable.com/security/research/tra-2026-38)，在 `src/LibsslTLSContext.cc` 客户端上下文显式强制 `X509_PURPOSE_SSL_SERVER`（`X509_VERIFY_PARAM_set_purpose`），并在 `scripts/test-http-tls.py` 增加 `clientAuth`-only 证书拒绝用例。
- [ ] **评估 2026 上游新报内存安全 Issue**：持续跟进 [aria2/aria2/issues](https://github.com/aria2/aria2/issues) 中的 `#2384`（`DefaultPieceStorage::markPiecesDone` UAF）、`#2385`（`getNumPieces` 负值强转）与 `#2411`（Torrent Poisoning）。

### P1 — 依赖升级与小幅正确性修复

- [ ] **OpenSSL 3.5.10 依赖升级**：待上游发布 OpenSSL `3.5.10` 后更新 `build-aux/dependencies.tsv` 及 SHA-256，清零 2026-11 披露的 8 个 Low CVE（可由 `check-dependencies.yml` 自动提醒）。
- [ ] **OpenSSL 3.x 版本号显示修复**：拉取 `src/FeatureConfig.cc` 精确上下文后修复 `aria2c --version` 将 `3.5.9` 显示为 `3.5.0i` 的问题。
- [ ] **核查 `parseUIntNoThrow` 上界（PR #2349）**：核查 `parseLong` 对负号字符串的边界行为（尤其 Windows LLP64 32 位 `unsigned long`）后再决定是否合入。

### P2 — 跨平台与功能扩展

- [ ] **Windows ARM64（`aarch64-w64-mingw32`）**：基于 [mstorsjo/llvm-mingw](https://github.com/mstorsjo/llvm-mingw)（UCRT）验证 autotools/libtool 与 LLD 链接兼容性并接入 CI。
- [ ] **Linux musl `-static-pie` ASLR 试点**：在容器内验证 `abcfy2/clang-cross-toolchain-ubuntu` 是否包含 `rcrt1.o` 及 `-fPIC` `libstdc++.a`；若具备条件，去掉 `ARIA2_STATIC=yes` 并改用 `-fPIE` + `-XCClinker -static-pie` 与 `readelf` 门禁。
- [ ] **CLI / Tracker / 代理增强**：按需核对 [PR #2363](https://github.com/aria2/aria2/pull/2363/files)（`-i -` 管道阻塞，需修正 `download_helper.cc` 括号语法并在本地源码验证）、[PR #2157](https://github.com/aria2/aria2/pull/2157)（同层 Tracker 轮换）及 [PR #2360](https://github.com/aria2/aria2/pulls)（原生 SOCKS5 代理）。

---

## 已完成

- [x] 2026-06 整理 `temp/*.md` → `docs/build-system-design.md` + `docs/TODO.md` + `docs/code-review.md`
- [x] 2026-06 仓库清理：建立 `.gitignore`，移除 `temp/`，去重 workflow，统一补丁目录
- [x] 2026-10 新增自动化测试流水线 `scripts/test.sh`，`full.yml` 和 `lite.yml` 均内置测试与 `verify-artifacts` 门禁
- [x] 2026-11 Round-1 增强补丁 `0007`–`0016`、`build-aux/` 依赖与工具链锁定、本地回环 HTTP/压缩/BT 测试与基准测试
- [x] 2026-11 Round-2 基础修复：修复 `0004` Win32 UB & `GetLastError()`、`0006` 宽字符指针 Bug & Win11/Server 2019–2025 识别；新增 `0017`（Nettle 4.0）；加固 `build.sh` 与维护工作流（SHA 锁定 + 默认分支保护）；修正 `test.sh` `--help=#http` 与 ELF NX 检查
- [x] 2026-11 Round-2 扩展（P0–P3）：新增 `0018`（CVE-2026-75421 `IOFile::getLine` 栈下溢）、`0019`（`Content-Disposition` 尾随分号，修正 PR #2153 `*eop` 越界）、`0020`（Y2038 `ServerStatMan` 64 位解析）；macOS `arm64` 升级为自包含静态依赖 + OpenSSL + `otool -L` 门禁 + `codesign`；Windows 嵌入 `longPathAware` 清单并随包附带 SHA-256 锁定 Mozilla `cacert.pem`；新增本地 HTTPS 回环测试 `scripts/test-http-tls.py` 与依赖自动巡检工作流 `check-dependencies.yml`
- [x] 2026-11 Round-2 补齐（P1–P3）：新增 `0021`（MinGW `#undef SIZE_MAX` 清理）、`0022`（BT `--remove-control-file`）、`0023`（PT `--show-files` 显示 `Private` 标志）
