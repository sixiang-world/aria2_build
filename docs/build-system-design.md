# aria2_build 构建系统方案

> 状态：**已实现** · 本文档源自 `temp/原先的项目的优点及实现方案.md`，整理为正式方案存档。

## 1. 项目定位

本项目是 [DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build) 的精简定制版，核心差异：**构建参数可由用户自定义**，而非原项目的一次性全平台构建。

## 2. 优点清单

### 2.1 用户可配置的构建参数（`workflow_dispatch` inputs）

原项目固定全量构建。本项目在 workflow 触发时允许：

- 选择目标平台（`linux-x86_64` / `linux-aarch64` / `windows-x86_64` / …）
- 指定 aria2 源码版本（branch / tag / commit）
- 控制是否静态编译 / 使用 zlib-ng / 使用 LibreSSL
- 附加自定义 `configure` 参数（lite 模式）

### 2.2 双模式构建（lite + full）

| 模式 | 文件 | 定位 |
|------|------|------|
| lite | `.github/workflows/lite.yml` | 轻量快速，直接用 Ubuntu 系统包编译，适合快速验证 |
| full | `.github/workflows/full.yml` | 完整功能，所有依赖从源码静态编译，支持 Linux / Windows / macOS 全平台 |

用户按需选择，不必等待全平台构建。

### 2.3 定时自动构建

`lite.yml` 与 `full.yml` 均在 `cron: "0 3 * * 1"`（每周一 UTC 03:00）触发，自动拉取最新 master 源码，保证产物常新。

## 3. 关键实现方案

### 3.1 workflow_dispatch 输入参数定义

```yaml
on:
  workflow_dispatch:
    inputs:
      aria2_ref:
        description: "Aria2 源码版本（tag 如 1.37.0，或 branch 如 master）"
        required: false
        default: "master"
      target:
        description: "目标平台（留空则构建全部）"
        required: false
        type: choice
        options: [ all, x86_64-unknown-linux-musl, ... ]
      enable_zlib_ng:   { default: "true" }
      enable_libressl:  { default: "false" }
  schedule:
    - cron: "0 3 * * 1"
  release:
    types: [ released ]
```

### 3.2 动态 matrix（full 模式）

用 `fromJSON` 表达式按用户选择的 `target` 动态展开 matrix，支持「全部」或「单平台」：

```yaml
matrix:
  cross_host: ${{ fromJSON(
    (github.event.inputs.target == 'all' || github.event.inputs.target == '')
    && '["arm-unknown-linux-musleabi", "aarch64-unknown-linux-musl", "x86_64-unknown-linux-musl", ...]'
    || format('["{0}"]', github.event.inputs.target)
  ) }}
```

### 3.3 参数透传到 build.sh

`full.yml` 复用上游 `build.sh`，通过环境变量传入用户选择：

```yaml
- name: compile
  env:
    CROSS_HOST:    "${{ matrix.cross_host }}"
    USE_LIBRESSL:  "${{ github.event.inputs.enable_libressl  || '0' }}"
    USE_ZLIB_NG:   "${{ github.event.inputs.enable_zlib_ng   || '1' }}"
    ARIA2_VER:     "${{ github.event.inputs.aria2_ref        || '' }}"
  run: |
    if [ "${GITHUB_EVENT_NAME}" = release ]; then
      export ARIA2_VER="${GITHUB_REF#refs/*/}"
      ARIA2_VER="${ARIA2_VER#v}"
      echo "ARIA2_VER=${ARIA2_VER}" >> "$GITHUB_ENV"
    fi
    chmod +x "${GITHUB_WORKSPACE}/build.sh"
    "${GITHUB_WORKSPACE}/build.sh"
```

> `build.sh` 的 `build_aria2()` 已支持 `ARIA2_VER` 非空时下载对应 release tarball，为空则用 master。

### 3.4 lite 模式 — 系统包快速编译

`lite.yml` 不依赖 Docker 交叉工具链，直接用 `apt-get` 装系统包，`git clone` 源码后 `git am` 应用补丁，再 `./configure && make`。

### 3.5 补丁应用注意事项

- **必须先配置 git 身份**，否则 `git am` 报 `Committer identity unknown`：
  ```yaml
  git config --global user.email "build@aria2-build"
  git config --global user.name "Aria2 Build"
  ```
- `working-directory` 已设置时，脚本内**不要再 `cd` 进同名目录**，否则双重嵌套。
- 补丁统一从仓库根目录的 `patch/*.patch` 读取（见 [code-review.md](./code-review.md) §5）。

## 4. 与 DoTheBetter 的差异总结

| 特性 | DoTheBetter | 本项目 |
|------|-------------|--------|
| 用户可配置参数 | ✗ | ✓ |
| 选择性构建平台 | ✗（全平台） | ✓（单平台/全部） |
| 定时构建 | ✓ | ✓ |
| Docker 交叉编译 | ✓ | ✓（full 模式） |
| macOS 支持 | ✗ | ✓（full 模式，AppleTLS） |
| Release 自动发布 | ✓ | ✓（continuous 预发布 + tag 正式发布） |
| 下载缓存 | ✓ | ✓ |
| build_info 生成 | ✓ | ✓ |
| build.sh 复用 | ✓ | ✓ |

## 5. 参考实现路径

源草稿见（已从仓库移除，仅本仓库历史中保留）：

- `temp/原先的项目的优点及实现方案.md` —— 优点规格
- `temp/移植提示词.md` —— 给 AI 助手的迁移提示词
