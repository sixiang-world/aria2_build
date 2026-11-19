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
│   ├── full.yml            # 全平台自包含静态构建 + 测试 + 发布（主力）
│   ├── lite.yml            # Linux 快速构建 + CppUnit + 测试 + 发布
│   ├── prepare-source.yml  # 解析提交、打补丁、打包和校验源码
│   ├── check-dependencies.yml        # 定期巡检 build-aux/dependencies.tsv 上游更新
│   ├── Delete_old_workflow_runs.yml  # 工具：清理旧 run
│   └── Clear_Repository_History.yml  # 工具：清空默认分支历史（高危，需默认分支 + CLEAR-HISTORY）
├── build-aux/              # 上游提交、依赖和交叉编译镜像锁 + Windows 长路径清单
├── patch/                  # 从 0001 开始依序应用的源码补丁（当前 0001–0023）
├── scripts/                # 源码准备、依赖拉取/巡检、矩阵生成、测试与基准脚本
│   └── test.sh             # 架构、链接、NX 硬化与 HTTP/TLS/压缩/BT 回环测试
├── build.sh                # Full 流水线交叉编译主脚本
├── docs/                   # 正式文档
├── README.md
└── AGENTS.md               # 本文件
```

## 3. 两条流水线的区别

| | `full.yml` | `lite.yml` |
|---|---|---|
| 目的 | 正式发布，全平台自包含静态构建 | 快速验证与 CppUnit 回归，仅 Linux |
| 工具链 | Docker 交叉编译镜像（Linux/Win）+ macOS-15 静态依赖 | 宿主 Ubuntu 系统包 |
| Aria2 源码 | 共用 `prepare-source.yml` | 共用 `prepare-source.yml` |
| macOS | ✓（OpenSSL/LibreSSL，第三方依赖全静态 + `otool -L` 门禁 + `codesign`） | ✗ |
| Windows | ✓（MinGW OpenSSL/LibreSSL 静态，含 `longPathAware` 清单与 `cacert.pem`） | ✗ |
| **内置测试** | ✓（QEMU/Wine/原生 + `scripts/test.sh`） | ✓（CppUnit + `scripts/test.sh`） |
| **发布门禁** | ✓（needs: 测试 + verify-artifacts） | ✓（needs: build 含测试 + verify-artifacts） |

## 4. 改 workflow 与补丁时的硬性约束

1. 所有构建使用 `scripts/aria2-source.sh` 的同一条补丁路径（`git apply --index`），失败立即停止。
2. GitHub Actions 每次只准备一次 Aria2 源码，各矩阵任务验证归档 SHA-256 再解包。
3. **`working-directory` 与脚本内 `cd` 不要重复**。
4. **所有第三方 Action 必须锁定完整 40 位 Commit SHA**，并显式声明最小 `permissions`。
5. **补丁路径**统一用 `${GITHUB_WORKSPACE}/patch`；新增补丁编号续接 `patch/aria2-00NN-<scope>-<short-desc>.patch`。
6. **`test.sh` 默认值断言**：`#basic` 选项从 `--help` 读取，`#http` 选项（如 `--connect-timeout`、`--retry-wait`）从 `--help=#http` 读取。
