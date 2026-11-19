# AGENTS.md

本文件为在本仓库中工作的 AI 编码助手（Claude / Codex / Cursor / Copilot 等）提供上下文。
人类开发者也可作为项目导览阅读。

---

## 1. 仓库是什么

这是 aria2 的**静态构建发布仓库**——不存放 aria2 源码，而是用 GitHub Actions 拉取上游 aria2 源码、打补丁、交叉编译出各平台静态二进制并发布 Release。

**上游血统**（两支汇合）：
- 构建工具链镜像：[abcfy2/aria2-static-build](https://github.com/abcfy2/aria2-static-build)（`ghcr.io/abcfy2/*` 锁定在 `build-aux/toolchains.tsv`）
- Workflow 框架：[DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build) → 本仓库在此之上重构为**版本锁定、SHA-256 校验、带回环测试门禁、支持用户可配置参数**的构建体系

`build.sh` 已针对 `build-aux/dependencies.tsv`、`scripts/fetch-dependency.sh` 与 `scripts/aria2-source.sh` 独立维护；修改时请确保与 `full.yml` 和本地容器构建保持一致。

## 2. 目录结构

```
.
├── .github/workflows/      # CI 流水线
│   ├── full.yml            # 全平台静态构建 + 测试 + 发布（主力）
│   ├── lite.yml            # Linux 快速构建 + 测试 + 发布
│   ├── prepare-source.yml  # 解析提交、打补丁、打包和校验源码
│   ├── Delete_old_workflow_runs.yml   # 工具：清理旧 run
│   └── Clear_Repository_History.yml   # 工具：清空 git 历史（高危，需输入 CLEAR-HISTORY）
├── build-aux/              # 上游提交、依赖和交叉编译镜像锁
├── patch/                  # 从 0001 开始依序应用的源码补丁（当前 0001–0017）
├── scripts/                # 源码准备、矩阵生成、测试与基准脚本
│   └── test.sh             # 架构、链接、NX 硬化与回环功能测试，支持 QEMU/Wine
├── build.sh                # Full 流水线交叉编译主脚本
├── docs/                   # 正式文档
│   ├── build-system-design.md   # 构建系统设计方案（已实现）
│   ├── distribution.md          # 源码、署名与依赖合规说明
│   ├── feature-inventory.md     # 功能来源、取舍与验证对照表
│   ├── TODO.md                  # 待办与已知问题
│   └── code-review.md           # 代码审查记录
├── README.md
└── AGENTS.md               # 本文件
```

注意：
- **补丁目录只有 `patch/`**。新建补丁请放 `patch/`，命名遵循 `patch/aria2-00NN-<scope>-<short-desc>.patch`。
- **正式 workflow 只有 `full.yml` + `lite.yml`**（共用 `prepare-source.yml`）。
- `temp/` 是 AI 草稿目录，已在 `.gitignore` 中，**不要 commit**。

## 3. 两条流水线的区别

| | `full.yml` | `lite.yml` |
|---|---|---|
| 目的 | 正式发布，全平台静态（macOS 当前为动态） | 快速验证与 CppUnit 回归，仅 Linux |
| 工具链 | Docker 交叉编译镜像（`toolchains.tsv`） | 宿主 Ubuntu 系统包 |
| Aria2 源码 | 共用 `prepare-source.yml` | 共用 `prepare-source.yml` |
| 触发器 | dispatch / push / PR / schedule / release | dispatch / push / PR / schedule |
| macOS | ✓（AppleTLS，动态） | ✗ |
| Windows | ✓（MinGW OpenSSL / LibreSSL 静态） | ✗ |
| **内置测试** | ✓（QEMU/Wine + `scripts/test.sh`） | ✓（CppUnit + `scripts/test.sh`） |
| **发布门禁** | ✓（needs: 测试 + verify-artifacts） | ✓（needs: build 含测试 + verify-artifacts） |

### 3.1 测试流水线（构建 → 测试 → 发布）

两条流水线都内置了 `scripts/test.sh` 驱动的综合测试，在编译完成后、发布前执行：

- **Linux musl 构建**：在 Docker 容器内用 QEMU（aarch64/arm/loongarch64）或原生执行（x86_64/i686）测试；MIPS 目标仅做架构与静态/NX 检查。
- **Windows 构建**：在容器内用 Wine 测试 `.exe`。
- **macOS 构建**：在 macOS runner 上原生测试。
- **Lite 构建**：各自使用原生 x86_64 和 ARM64 Ubuntu runner，并在 x86_64 上运行完整上游 CppUnit 测试集。

`test.sh` 验证可执行性、架构、链接方式、ELF NX 堆栈与默认值，并运行 HTTP Range、重试、续传、压缩和 BT 回环测试。

**改测试脚本时的约束**：
- `test.sh` 必须支持 `--runner <qemu-arch|wine>` 参数，且 `--runner` 为空时原生执行。
- 公网 HTTPS 探测允许因网络限制跳过。回环测试失败会阻断构建。

## 4. 改 workflow 时的硬性约束（踩过的坑）

1. 所有构建使用 `scripts/aria2-source.sh` 的同一条补丁路径。脚本用 `git apply --index` 应用队列，失败立即停止。

2. GitHub Actions 每次只准备一次 Aria2 源码。各矩阵任务验证归档的 SHA-256 再解包。

3. **`working-directory` 与脚本内 `cd` 不要重复**：已设 `working-directory: aria2-src` 时，脚本里再 `cd aria2-src` 会双重嵌套导致路径错误。

4. **所有第三方 Action 必须锁定完整 40 位 Commit SHA**，并显式声明最小 `permissions`。

5. **补丁路径**：统一用 `${GITHUB_WORKSPACE}/patch`（不是 `.github/patches`）。

6. **不要给同一 cron 挂两个内容相同的 workflow**——会双重构建。

## 5. 验证和历史记录

功能和已知限制见 [功能对照表](docs/feature-inventory.md)。[待办](docs/TODO.md) 和 [代码审查](docs/code-review.md) 记录各轮审查与待办事项。

## 6. 工作约定

- **新增补丁**：编号续接 `patch/aria2-00NN-<scope>-<short-desc>.patch`，并在 `docs/feature-inventory.md` 与 `README.md` 登记。
- **改 workflow**：改完用 YAML 解析器过一遍语法（注意 `${{ }}` 表达式会让标准 parser 报错，需剥离后再验）。
- **文档先行**：设计/方案类内容写进 `docs/`，不要塞 `temp/`（被 gitignore）。
- **提交**：commit message 用 Conventional Commits（`feat:` / `fix:` / `chore:` / `docs:`），中文描述可。
- **不要**把构建产物（`release/`、`downloads/`、`*.zip`、`build_info.md`）提交进仓库——已在 `.gitignore`。

## 7. 快速验证命令

```bash
# YAML 语法快速检查（剥离 ${{ }} 后）
python3 -c "import yaml,re,sys; yaml.safe_load(re.sub(r'\\$\\{\\{.*?\\}\\}', '\"\"', open(sys.argv[1]).read()))" .github/workflows/full.yml

# 本地复现某平台构建
docker run --rm -v "$(pwd):/work" -w /work \
  -e CROSS_HOST=x86_64-unknown-linux-musl \
  ghcr.io/abcfy2/clang-cross-toolchain-ubuntu:x86_64-unknown-linux-musl ./build.sh
```
