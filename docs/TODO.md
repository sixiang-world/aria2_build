# TODO

> 跟踪本仓库尚未完成 / 待改进的事项。已完成项归档到各文件末尾的「已完成」小节。

## 待办（按优先级）

### P0 — 正确性 / 会直接导致构建失败

- [ ] **统一补丁目录**：当前 `patch/` 与 `.github/patches/` 两份内容相同但行尾不同（CRLF vs LF）的补丁并存。
  - 决策：保留仓库根 `patch/`（与 `build.sh` 第 477–481 行、`full.yml` macOS job、`bak/` 保持一致），删除 `.github/patches/`。
  - 同步修改 `lite.yml` 第 70 行 `PATCH_DIR="${GITHUB_WORKSPACE}/.github/patches"` → `…/patch`。
- [ ] **删除重复 workflow**：`aria2_build_and_release.yml` 与 `full.yml` 几乎逐字相同，且二者都在同一 `schedule`（`0 3 * * 1`）触发，会导致**每周重复构建一次完整流水线**。保留 `full.yml`，删除 `aria2_build_and_release.yml`。

### P1 — 仓库卫生

- [x] 建立 `.gitignore`，防止 `temp/`、`*.backup`、`release/`、`downloads/` 等被追踪。
- [x] 从 git 移除 `temp/`（草稿文档已整理为正式文档进 `docs/`）。
- [ ] 删除 `full.yml.backup`（未追踪的本地残留）。
- [ ] 处理 `bak/` 下 4 个旧 workflow：确认不再需要后删除（已被 `full.yml` 取代）。
- [ ] 处理 `Clear_Repository_History.yml` 文件中的 GBK 乱码注释（重新以 UTF-8 保存或删除注释）。

### P2 — 可选改进

- [ ] `lite.yml` 的 prerelease `body` 里用了 `$(date --utc)`，但 `body:` 是 YAML 字面量，shell 命令**不会被执行**，会原样出现。改用 `run` 步骤先生成 body 文件再 `body_path:`。
- [ ] `lite.yml` `linux-aarch64` 选项存在，但 matrix 始终两平台全跑、且 host 交叉编译在 lite 流程里未必跑通——考虑限制 lite 仅 x86_64，或补上 aarch64 的依赖安装。
- [ ] 考虑给 `docs/` 加一个 README 索引。

---

## 已完成

- [x] 2026-06 整理 `temp/*.md` → `docs/build-system-design.md` + `docs/TODO.md` + `docs/code-review.md`
- [x] 2026-06 仓库清理：建立 `.gitignore`，移除 `temp/`，去重 workflow，统一补丁目录（见本文件 P0/P1 各项的勾选状态以最新提交为准）
