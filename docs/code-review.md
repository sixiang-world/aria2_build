# 代码审查 — 2026-06-14 & 2026-11-18

审查范围：`.github/workflows/*.yml`、`build.sh`、`build-aux/*`、`patch/*`、`scripts/*`、仓库文档与整体结构。

严重度图例：🔴 阻断 / 🟠 应修 / 🟡 建议 / 🔵 提示

---

## Round 2 深度审查 — 2026-11-18

### 🟠 R2-1. `patch/aria2-0004` MinGW `--daemon` 存在 Win32 未定义行为与错误吞没

**位置**：`patch/aria2-0004-option_processing-make-use-of-deamon-on-mingw.patch`

1. `CreateProcessW` 的 `lpCommandLine` 参数在 Win32 规范中允许被系统就地修改，原补丁传递 `const_cast<LPWSTR>(daemonCmdLine.c_str())` 属于 C++ 未定义行为（UB）。
2. `STARTUPINFOW si = {};` 未初始化必需字段 `si.cb = sizeof(si);`，且 `si.wShowWindow` 使用布尔值 `FALSE` 而非标准宏 `SW_HIDE`。
3. `CreateProcessW` 失败时静默继续在前台运行，未与 POSIX `daemon()` 分支一致返回错误。

**处理**：✅ 已修复——改用可写缓冲区 `&daemonCmdLine[0]`、补齐 `si.cb = sizeof(si)` 与 `SW_HIDE`，失败时通过 `GetLastError()` 输出 Win32 错误码并返回 `error_code::UNKNOWN_ERROR`。

---

### 🟠 R2-2. `patch/aria2-0006` 宽字符指针输出 Bug 及新版 Windows 识别缺失

**位置**：`patch/aria2-0006-feature-config-add-os-info-for-newer-windows.patch`

1. 将结构体升级为 `RTL_OSVERSIONINFOEXW` 后，`ovi.szCSDVersion` 变为 `WCHAR[128]`（UTF-16），但后续仍执行 `rv << " (" << ovi.szCSDVersion << ")";`，在 C++ 中会将 `wchar_t*` 以十六进制内存地址形式输出而非 Service Pack 文本。
2. 所有 `10.0` Workstation 均硬编码为 `"Windows 10"`、所有 `10.0` Server 均硬编码为 `"Windows Server 2016"`，未按 `dwBuildNumber` 区分 Windows 11 及 Server 2019/2022/2025。

**处理**：✅ 已修复——使用 `WideCharToMultiByte(CP_UTF8, ...)` 安全转换 `szCSDVersion`，并按微软官方 Build 号区分 Windows 11（`>= 22000`）与 Server 2019（`>= 17763`）/ 2022（`>= 20348`）/ 2025（`>= 26100`）。

---

### 🟠 R2-3. Nettle 4.0 兼容性缺口（上游 PR #2358）

**位置**：`patch/`（影响启用 `--with-libnettle` 的 macOS 及现代 Linux 发行版构建）

Nettle 4.0 移除了 `hash->digest(...)` 的长度参数，导致针对 Nettle 4.0 编译失败。

**处理**：✅ 已新增 `patch/aria2-0017-nettle-fix-build-with-nettle-4.patch`（同步自上游 PR #2358 / openSUSE Factory 精确补丁）。

---

### 🟠 R2-4. 跨平台 TLS 后端与 CA 证书可用性隐患（需决策）

1. **Windows Full 构建**（`build.sh`）：采用 `--without-wintls --with-openssl` 且 OpenSSL 配置 `--openssldir=/etc/ssl`，Windows 宿主不存在 `/etc/ssl`，导致不手动传 `--ca-certificate` / `SSL_CERT_FILE` 时 HTTPS 证书校验失败。
2. **macOS Full 构建**（`full.yml`）：采用 `--with-appletls`（上游 [Issue #2277](https://github.com/aria2/aria2/issues/2277) 报告部分 TLS 1.3 站点握手失败）且动态链接 7 个 Homebrew `.dylib`，在未安装 Homebrew 的 Mac 上无法运行。

**处理**：因涉及 TLS 后端或产物分发形态变更，保留现状并在 `docs/TODO.md` 与 `docs/feature-inventory.md` 明确记录方案，待用户确认后实施。

---

### 🟡 R2-5. 构建安全硬化、维护工作流供应链与文档卫生

1. `build.sh` 缺少编译/链接安全硬化参数及显式 `--without-gnutls`，且在 `mips*`（仅架构检查）与本地纯构建场景强制安装 `qemu-user`/`wine`。✅ 已添加 `-fstack-protector-strong -Wformat -Werror=format-security`、Linux `-Wl,-z,relro,-z,now -Wl,-z,noexecstack`、`--without-gnutls`、`INSTALL_TEST_RUNNERS` 开关及 MIPS 跳过逻辑。
2. `.github/workflows/Clear_Repository_History.yml` 与 `Delete_old_workflow_runs.yml` 未锁定 Action Commit SHA；前者缺少 `permissions` 和防误触确认且硬编码 `master`。✅ 已全部锁定 SHA、显式声明最小权限，并为清空历史增加 `CLEAR-HISTORY` 强制确认输入。
3. `scripts/test.sh` 仅检查了 5 项调优默认值（漏检 `--connect-timeout` 与 `--retry-wait`）且未检查 ELF NX 堆栈；`scripts/full-matrix.py` 解析 `toolchains.tsv` 未过滤空行/注释。✅ 已全部补齐。
4. `README.md` 第 5、117 行文档链接误写为 `https://www.google.com/search?q=docs/...`；`AGENTS.md` 与 `docs/TODO.md` 多处内容滞后。✅ 已修复并同步。

---

## Round 1 历史审查记录 — 2026-06-14 & 2026-10-13

- 阻断项 2 处（重复 workflow `aria2_build_and_release.yml`、重复补丁目录 `.github/patches/`）—— ✅ 已删除并统一。
- 应修项 2 处（`full.yml` matrix null 守卫、`lite.yml` prerelease body 字面量与 aarch64 构建）—— ✅ 已修复。
- 新增 `scripts/test.sh` 回环测试与 `verify-artifacts` 门禁、锁定 `build-aux/` 依赖与工具链镜像。
