# TODO

> 跟踪本仓库尚未完成 / 待改进的事项。已完成项归档到各文件末尾的「已完成」小节。

## 待办（按优先级）

### P0 — 正确性 / 会直接导致构建失败

- [x] **统一补丁目录**：当前 `patch/` 与 `.github/patches/` 两份内容相同但行尾不同（CRLF vs LF）的补丁并存。
  - 决策：保留仓库根 `patch/`，删除 `.github/patches/`。✅ 已完成。
- [x] **删除重复 workflow**：`aria2_build_and_release.yml` 与 `full.yml` 几乎逐字相同。✅ 已删除，只保留 `full.yml`。

### P1 — 仓库卫生

- [x] 建立 `.gitignore`，防止 `temp/`、`*.backup`、`release/`、`downloads/` 等被追踪。
- [x] 从 git 移除 `temp/`（草稿文档已整理为正式文档进 `docs/`）。
- [ ] 删除 `full.yml.backup`（未追踪的本地残留）。
- [ ] 处理 `bak/` 下 4 个旧 workflow：确认不再需要后删除（已被 `full.yml` 取代）。
- [ ] 处理 `Clear_Repository_History.yml` 文件中的 GBK 乱码注释（重新以 UTF-8 保存或删除注释）。

### P2 — 可选改进

- [x] `lite.yml` 的 prerelease `body` 里用了 `$(date --utc)`，但 `body:` 是 YAML 字面量，shell 命令**不会被执行**。✅ 已改用 `run` 步骤生成 `body.md` 再 `body_path: release/body.md`。
- [x] `lite.yml` `linux-aarch64` 缺少交叉编译器依赖。✅ 已添加 `gcc-aarch64-linux-gnu g++-aarch64-linux-gnu libc6-dev-arm64-cross`，并用 `qemu-user-static` 运行测试。
- [ ] 考虑给 `docs/` 加一个 README 索引。

---

## 已完成

- [x] 2026-06 整理 `temp/*.md` → `docs/build-system-design.md` + `docs/TODO.md` + `docs/code-review.md`
- [x] 2026-06 仓库清理：建立 `.gitignore`，移除 `temp/`，去重 workflow，统一补丁目录
- [x] 2026-10 新增自动化测试流水线 `scripts/test.sh`（7 项综合测试），`full.yml` 和 `lite.yml` 都内置测试阶段并让发布依赖测试通过
- [x] 2026-10 修复 `lite.yml` 已知问题（prerelease body 字面量、aarch64 交叉编译器缺失）
- [x] 2026-10 `full.yml` 新增 `verify-artifacts` job 做 ZIP 完整性验证，prerelease/release 依赖它
- [x] 2026-10 上游同步：build.sh 镜像源（CERNET）、libiconv（kernel.org）、c-ares（动态版本）、代理域名（gh-proxy.org）
- [x] 2026-10 恢复 MIPS 平台构建（mips/mipsel/mips64/mips64el），MIPS 仅做架构检查不做运行时测试（沿用上游策略）
