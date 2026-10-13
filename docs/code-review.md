# 代码审查 — 2026-06-14

审查范围：`.github/workflows/*.yml`、`build.sh`、`patch/`、仓库整体结构。

严重度图例：🔴 阻断 / 🟠 应修 / 🟡 建议 / 🔵 提示

---

## 🔴 1. 两个 workflow 共享同一 cron，导致每周双重全量构建

**位置**：`.github/workflows/full.yml` 与 `.github/workflows/aria2_build_and_release.yml`

二者除 `name:` 字段（"Aria2 Full Build" vs "ARIA2 Build and Release"）和若干空行外**逐字相同**，并且 `on.schedule` 都是 `0 3 * * 1`。结果：每周一 UTC 03:00 会触发**两次**完整流水线（Linux×6 + MinGW×2 + macOS×1 = 9 个 job × 2），白白消耗 2× Actions 额度，还会连续覆盖 `continuous` release。

**处理**：删除 `aria2_build_and_release.yml`，只保留 `full.yml`。

> 验证命令：`git diff --no-index .github/workflows/full.yml .github/workflows/aria2_build_and_release.yml` 仅 `name` + 空行差异。

---

## 🔴 2. 补丁目录有两份，内容相同但行尾不同

**位置**：`patch/`（6 个文件） vs `.github/patches/`（6 个文件）

MD5 不一致，但 `git diff --no-index --ignore-all-space` 显示**内容完全相同**——差异仅来自 CRLF vs LF。

- `build.sh:477-481`、`full.yml:209`（macOS job）、`aria2_build_and_release.yml:211`、`bak/*.yml` 全部读 `patch/`。
- **只有** `lite.yml:70` 读 `.github/patches/`。

**处理**：删除 `.github/patches/`，把 `lite.yml` 改为读 `patch/`，与全仓库统一。

---

## 🟠 3. `full.yml` MinGW job 的 matrix 在 schedule/release 事件下恒为空数组

**位置**：`.github/workflows/full.yml:118`

```yaml
cross_host: ${{ fromJSON(
  (github.event.inputs.target == 'all' || github.event.inputs.target == '')
  && '["x86_64-w64-mingw32","i686-w64-mingw32"]'
  || (contains(fromJSON('["x86_64-w64-mingw32","i686-w64-mingw32"]'), github.event.inputs.target)
      && format('["{0}"]', github.event.inputs.target) || '[]')) }}
```

- `schedule` / `release` 事件下 `github.event.inputs` 为 null，`github.event.inputs.target` 求值为空串 `''`，第一个分支成立 → 正常返回 `["x86_64-w64-mingw32","i686-w64-mingw32"]`。✓ **逻辑无误**。
- 但表达式极其晦涩，且 Linux job（第 45 行）用的是更简单的两段式写法。**建议**：把 MinGW job 的表达式与 Linux job 对齐，靠 job 级 `if: contains(...)` 过滤非 Windows 的 target，而不是塞进 matrix 表达式。可读性显著提升，行为不变。

---

## 🟠 4. `lite.yml` prerelease 的 `body:` 含不会被求值的 shell 命令

**位置**：`.github/workflows/lite.yml:176-182`

```yaml
body: |
  ## Aria2 Lite Build
  ...
  - 构建时间: $(date --utc)        # ← 不会执行，会原样输出字面量
  - Aria2 版本: ${{ needs.build.outputs.ARIA2_VERSION || 'latest' }}  # ← build job 没有 outputs
```

两个问题：
1. `body:` 是 YAML 字面量字符串，`$(date --utc)` 不会被 shell 展开，会以字面文本写进 release 说明。
2. `build` job 没有 `outputs:` 块，`needs.build.outputs.ARIA2_VERSION` 恒为空，永远显示 `latest`。

**处理**：在上一步用 `run` 生成 `body.md`（写入真实时间与版本），再用 `body_path: release/body.md`。

---

## 🟡 5. `lite.yml` 三个 job 都依赖 `linux-aarch64`，但流水线对 aarch64 未必可用

`matrix` 写死两个 target（x86_64 + aarch64），aarch64 用 `--host=aarch64-linux-gnu` 交叉编译，但 `apt-get install` 列表里**没有** `gcc-aarch64-linux-gnu` / `g++-aarch64-linux-gnu`，configure 阶段会因找不到交叉编译器失败。

**建议**：lite 模式只保留 `linux-x86_64`；或为 aarch64 单独加交叉工具链安装步骤。

---

## 🟡 6. `Clear_Repository_History.yml` 注释是 GBK 乱码

文件以 GBK 编码写了中文注释，在 UTF-8 环境显示为乱码（如 `鍏佽鎵嬪姩瑙﹀彂`）。GitHub 网页端同样会乱码。

**处理**：用 UTF-8 重写注释，或直接删除该 workflow（清空 git 历史是高危操作，默认禁用即可）。

---

## 🟡 7. `temp/` 被追踪进版本库

`temp/原先的项目的优点及实现方案.md`、`temp/移植提示词.md` 作为草稿被 `git add` 提交。AI 工作目录草稿不应进入公开仓库。

**处理**：`git rm -r --cached temp/` 并删除目录，内容已整理到 `docs/`。`.gitignore` 已加 `temp/`。

---

## 🔵 8. `aria2_build_and_release.yml` 在 git 历史中

即便删除文件，历史里仍可查到。若 `temp/` 草稿含敏感信息需彻底清除，可用 `Clear_Repository_History.yml` 或 `git filter-repo`。当前内容无敏感信息，**仅作提示**。

---

## 🔵 9. `bak/` 4 个旧 workflow 已被取代

`.github/workflows/bak/{build_and_release,linux-aria2,mac-aria2,windows-aria2}.yml` 是分平台拆分前的旧版，已被 `full.yml` 的单文件 matrix 方案取代。保留会增加维护噪音，建议删除或移出 `.github/workflows/`（放别处不会被 Actions 自动加载）。

---

## 审查结论

- 阻断项 2 处（#1 重复 workflow、#2 补丁目录重复）—— ✅ 已处理。
- 应修项 2 处：
  - #3 matrix 表达式 —— 本轮在 `full.yml` 中补充了 `null` 守卫（`github.event.inputs.target == null`），避免 schedule 事件下的边界问题。
  - #4 lite body 字面量 —— ✅ 已修复，改用 `run` 步骤生成 `body.md` + `body_path`。
- 新增：自动化测试流水线 `scripts/test.sh`，覆盖 7 项检查（版本/架构/静态链接/魔改默认值/HTTP 下载/多连接/断点续传），`full.yml` 和 `lite.yml` 均内置测试阶段，发布依赖测试通过。
- 新增：`full.yml` 的 `verify-artifacts` job 做跨产物 ZIP 完整性验证。
- 其余为卫生/可读性问题，逐步收敛即可。

---

## 2026-10-13 上游同步

对比上游 `abcfy2/aria2-static-build` 最新 `build.sh`（截至 2026-10-07）后，同步了以下变更：

| 变更 | 说明 | 上游 commit |
|------|------|-------------|
| Ubuntu 镜像源 `mirrors.bfsu.edu.cn` → `mirrors.cernet.edu.cn` | BFSU 镜像不稳定，CERNET 更可靠 | 2026-10-01 |
| libiconv 下载源 `ftpmirror.gnu.org` → `mirrors.kernel.org/gnu`（+ CERNET 镜像） | ftpmirror 不稳定，改用固定镜像 | 2026-10-01 |
| c-ares 版本从固定 `v1.34.5` → 动态获取最新 release | 临时 pin 已不再需要 | 2026-08-21 |
| 代理域名 `gh-proxy.com` → `gh-proxy.org` | 旧域名失效 | 近期 |
| MIPS 平台恢复 | 上游从 clang-cross 切回 musl-cross，恢复 mips/mipsel/mips64/mips64el | 2026-10-07 |

**保留的定制差异**（我们有、上游没有的）：
- `patch/` 目录自动应用魔改补丁（核心特性）
- 构建后 `file` + `ldd` 验证（架构 + 静态链接检查）
- `build_info.md` 中写入二进制 `file` 信息

**上游 workflow 变化**：上游仍使用单一 `build_and_release.yml`，actions/checkout 已升到 v6。我们已使用 v6/v7，无需额外同步。

`build.sh` 本身（取自上游 abcfy2/aria2-static-build，保留补丁路径定制 + 构建后验证增强）已同步至最新。
