# Aria2 增强功能清单与验证记录

> 更新于 2026-11-18。本表明确区分 **已有实现**、**当前分支改进** 与 **待研究/验证**。
> 这是构建/补丁分发仓库，aria2 引擎源码来自上游；未在 CI/实机验证的项目不得声称已完成。

## 已有增强及本轮工程改进

| 功能 | 主要来源 | 状态 | 当前验证方式 / 限制 |
|---|---|---|---|
| 取消单服务器连接数上限、调整分片和并发默认值 | DoTheBetter/aria2_build；上游参考 abcfy2 | 已有 `patch/0002` | `scripts/test.sh` 检查帮助默认值、分片下载；需增加本地 HTTP Range 服务器来独立验证上限 |
| 慢速及连接重置后重试 | DoTheBetter、P3TERX | 已有 `patch/0003` | 目前缺少受控故障注入，不应视作功能已验证 |
| HTTP 400/403/406 重试选项 | DoTheBetter、P3TERX | 已有 `patch/0005` | 需要受控返回码测试；谨慎处理重试风暴及服务器限流 |
| 默认路径调整 | DoTheBetter | 已有 `patch/0001` | 待逐项断言配置和 DHT 文件路径行为 |
| MinGW daemon 行为 | DoTheBetter | 已有 `patch/0004` | Wine 构建验证不等同 Windows 实机服务验证 |
| 新版 Windows OS 信息 | DoTheBetter | 已有 `patch/0006` | 需 Windows 实机测试 |
| Linux、Windows、macOS 构建 | abcfy2、DoTheBetter、本仓库 | 已有 Full | 2026-11-09 Full 成功；2026-11-16 Full macOS cancelled、Linux/Windows 成功 |
| Lite x86_64/aarch64 | 本仓库 | 修复中 | 2026-11-16 两平台报 gettext 0.19/0.22 基础设施不匹配；本分支尝试统一生成版本，待 Actions 验证 |
| `patched` / `vanilla` | 本分支 | 已提交代码、待 CI | Full、Lite 和测试均增加开关；默认保持 patched |
| APT HTTPS 证书验证 | 本分支 | 已提交代码、待 CI | 删除关闭 Verify-Peer/Verify-Host 的设置，不再清空原 APT 配置 |
| 补丁失败即停止 Lite | 本分支 | 已提交代码、待 CI | 使用 `git am --3way`，失败时 abort + 退出；此前失败可能被 `|| true` 吞掉 |
| 明确 PASS/SKIP/FAIL | 本分支 | 已提交代码、待 CI | 网络不可达不再被冒充为 PASS；SKIP 仍不阻断，后续应建设确定性离线集成测试 |
| 目标平台过滤和发布门禁 | 本分支 | 已提交代码、待 CI | Full 按 Linux/MinGW/macOS 分组，验证任务依赖实际构建任务，待 Actions 验证 |

## 有真实补丁证据、但尚未合并的候选

| 候选 | 源代码或项目 | 判断 | 迁移难度 |
|---|---|---|---|
| HTTP raw-deflate 非标准服务器兼容 | [Elypha/aria2-mod 0007](https://github.com/Elypha/aria2-mod/blob/master/aria2-patch/0007-retry-raw-deflate-mode.patch) | 具备新增价值，但原实现遇到解码错误就切换 raw 模式，需检查流状态、输出回滚和测试后才可合并 | 中 |
| WinTLS/Schannel TLS 后端 | [DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build)；[Elypha/aria2-mod](https://github.com/Elypha/aria2-mod) | 优先评估为 Windows 可选后端；当前 Full `build.sh` 明确使用 `--without-wintls`，README 中的 WinTLS 声称尚不成立 | 中高 |
| 不发送 Want-Digest 的选项 | [P3TERX/Aria2-Pro-Core 0004](https://github.com/P3TERX/Aria2-Pro-Core/blob/master/patch/0004-option-add-option-to-disable-want-digest-header.patch) | **不建议直接移植**：Elypha 指出 aria2 1.37.0 已提供 `--no-want-digest-header`；先复核上游，避免重复实现 | 低 |
| 更激进的 128 默认连接配置 | [hosxy/aria2-fast](https://github.com/hosxy/aria2-fast) | 已有解除上限能力；默认 128/更高不意味着更快，可能增加 CPU 和服务器负担；建议仅作为可配置 profile | 低 |
| 内存分配器（tcmalloc）静态构建 | [SKIYET/Aria2-Static-Build-WithTCmalloc](https://github.com/SKIYET/Aria2-Static-Build-WithTCmalloc) | 尚无基准证明性能收益；先对比吞吐、RSS、CPU、碎片，再决定是否新增 optional backend | 中 |

## 需要继续解决的工程问题

1. **版本与 provenance**：Full 的 `aria2_ref` 目前仅可靠处理 `master` 与正式发布 tarball 版本号，不能据此声称支持任意 SHA；产物命名还会查询最新上游 Release，可能与实际编译源码不一致。
2. **WinTLS 与依赖关系**：需要识别 libssh2、OpenSSL、Windows 平台配置是否允许无冲突地切换后端。
3. **受控集成测试**：用本地 HTTP 服务器模拟 206 Range、400/403/406、429、断连、低速、断点续传、错误校验；BT/DHT 测试采用隔离资源，不依赖不稳定公网。
4. **供应链审计**：确认依赖版本、签名/哈希、编译镜像 digest，避免直接执行动态下载的未经核验代码。
5. **多平台性能测量**：吞吐、首字节延迟、CPU、RSS、连接数、失败恢复率；对比 aria2 原版及增强版，相同场景重复运行。不可仅凭“解除限制”认定速度更快。
6. **发布安全**：当前发布任务会删除现有 `continuous` Release/tag；正式发布还存在删除现有 tag/release 的逻辑。修改此破坏性策略前应单独设计并征求用户同意。

## 测试证据

- [2026-11-09 Full 成功](https://github.com/sixiang-world/aria2_build/actions/runs/42601173936)
- [2026-11-16 Full 部分成功、macOS 取消](https://github.com/sixiang-world/aria2_build/actions/runs/43847034660)
- [2026-11-16 Lite 失败](https://github.com/sixiang-world/aria2_build/actions/runs/43849266794)

> 本分支代码已写入 GitHub，**但本地运行环境无法访问 github.com，也没有 Docker；未声称完成全平台构建和性能基准测试**。后续须以 PR 上 Actions 的实际日志为准。
