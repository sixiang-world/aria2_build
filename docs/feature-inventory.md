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

## 已核查的外部实现

| 候选 | 源代码或项目 | 判断 | 迁移难度 |
|---|---|---|---|
| HTTP raw-deflate | [Elypha/aria2-mod 0007，Joseph Chris](https://github.com/Elypha/aria2-mod/blob/941a5db1c7f3e6e26249aeceedbf7023a8d0aa36/aria2-patch/0007-retry-raw-deflate-mode.patch) | 已独立实现 `patch/0007`。在写出前选择解码格式，沿用上游文件的许可证和 OpenSSL 例外。头部与有效 zlib 包装冲突的裸流按 zlib 处理 | 已检查稳定版和 master 的补丁上下文，编译与运行待验证 |
| BT Tracker 全轮询与重试 | [qydysky/aria2_patch](https://github.com/qydysky/aria2_patch/tree/0feb0126117d334d6038bb3dc10402b4541f3669) | 待设计。现有补丁把成功应答按失败推进，会改变 announce 事件状态。其重试补丁把相同的 `retry-wait` 值写回已复制的 Option | 待用本地 HTTP/UDP Tracker 验证 |
| Windows ARM64 | [minnyres/aria2-windows-arm64](https://github.com/minnyres/aria2-windows-arm64/tree/08e701b09516558c8c5ef4ce314936f14e2f3575) | 待评估 LLVM-MinGW / vcpkg 工具链 | 未接入矩阵 |
| WinTLS/Schannel TLS 后端 | [DoTheBetter/aria2_build](https://github.com/DoTheBetter/aria2_build)；[Elypha/aria2-mod](https://github.com/Elypha/aria2-mod) | 优先评估为 Windows 可选后端；当前 Full `build.sh` 明确使用 `--without-wintls`，README 中的 WinTLS 声称尚不成立 | 中高 |
| 不发送 Want-Digest 的选项 | [P3TERX/Aria2-Pro-Core 0004](https://github.com/P3TERX/Aria2-Pro-Core/blob/master/patch/0004-option-add-option-to-disable-want-digest-header.patch) | **不建议直接移植**：Elypha 指出 aria2 1.37.0 已提供 `--no-want-digest-header`；先复核上游，避免重复实现 | 低 |
| 更激进的 128 默认连接配置 | [hosxy/aria2-fast](https://github.com/hosxy/aria2-fast) | 已有解除上限能力；默认 128/更高不意味着更快，可能增加 CPU 和服务器负担；建议仅作为可配置 profile | 低 |
| 内存分配器（tcmalloc）静态构建 | [SKIYET/Aria2-Static-Build-WithTCmalloc](https://github.com/SKIYET/Aria2-Static-Build-WithTCmalloc) | 尚无基准证明性能收益；先对比吞吐、RSS、CPU、碎片，再决定是否新增 optional backend | 中 |

## 云端接手

从 [草稿 PR #1](https://github.com/sixiang-world/aria2_build/pull/1) 的 `feat/aria2-reliability-and-patch-modes-20261118` 分支继续。现有六个补丁与 [myfreeer 的补丁](https://github.com/myfreeer/aria2-build-msys2/tree/ce79080f2fc66aa4d233fd937cb58901c9f95087) 逐字节一致，已覆盖 MinGW daemon、默认路径和新版 Windows 系统信息。

1. 用同一 upstream ref 构建 `patched` 和 `vanilla`。先用下面的回环测试验证 `patch/0007`，再把它接入发布门禁。
2. 确认 Lite gettext 修复，并统一 Full/Lite/macOS 的源码解析、构建提交记录和产物命名。以同一次运行解析出的 upstream SHA 构建所有目标。
3. 恢复 Windows 可选 WinTLS，验证 Schannel、SFTP、证书信任和对应产物标记。随后扩展本地 HTTP 故障场景、BT Tracker 测试及可重复基准。
4. 发版前核对对应源码归档和静态依赖的分发材料。待补充依赖版本和完整性校验。

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
- [PR #1 前一版 Full CI](https://github.com/sixiang-world/aria2_build/actions/runs/44317682005) 通过 Linux x86_64、Linux aarch64、Windows x86_64 和 ZIP 检查，macOS 跳过。
- [2026-11-16 Lite 失败](https://github.com/sixiang-world/aria2_build/actions/runs/43849266794)

- `patch/0007` 对 upstream `release-1.37.0` 及 master 快照 `9e7273583f83e881e3ec067b523ba88724088d2f` 检查过补丁上下文。本地编译中断，解压测试与性能基准待执行。

```bash
python3 scripts/test-http-encoding.py path/to/patched/aria2c
python3 scripts/test-http-encoding.py path/to/vanilla/aria2c --baseline
```

回环测试覆盖 gzip、zlib 包装、裸流、单字节分块、损坏的 zlib 校验和，以及错误标为 gzip 的裸流。测试脚本尚未接入 Actions。
