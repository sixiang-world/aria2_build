# 源码、署名与依赖

Full 和 Lite 从同一个准备任务接收本次构建的 Aria2 源码归档。归档包含应用补丁后的完整 Git 源码树、上游许可证、补丁队列、构建脚本和依赖锁。归档中的 `SOURCE-PROVENANCE.txt` 记录上游提交、源码树和构建仓库提交。正式产物的 `SHA256SUMS` 同时覆盖二进制和这份源码归档。

## Aria2 与补丁

- Aria2 按上游源码所示的 GPL-2.0-or-later 分发。保留 `COPYING`、`LICENSE.OpenSSL`、`AUTHORS` 和各源文件的声明。现有补丁保留原提交作者，新引入的上游补丁保留原作者。独立实现的参考来源见补丁说明及[功能对照表](feature-inventory.md)。
- `LICENSE.OpenSSL` 记录的是历史 OpenSSL 许可证例外。对使用 Apache-2.0 版 OpenSSL 3 的组合，分发者应核实链接组件允许 GPLv3，并按 GPLv3 兼容的条款提供二进制、源码和许可证材料。[上游例外](https://github.com/aria2/aria2/blob/9e7273583f83e881e3ec067b523ba88724088d2f/LICENSE.OpenSSL) · [OpenSSL 许可证](https://www.openssl.org/source/license.html) · [GNU 许可证列表](https://www.gnu.org/licenses/license-list.html#apache2)
- 原有构建仓库和部分参考项目没有独立可核实的许可证声明。新增补丁优先采用具有明确许可的 Aria2 源文件或独立实现，保留已存在的署名与历史。

## 静态依赖

Full 在 [依赖锁](../build-aux/dependencies.tsv) 中记录直接构建依赖的版本、SHA-256 和下载位置。每个构建的 `build_info.md` 记录实际使用的依赖和工具链。Full 静态 ZIP 的 `THIRD-PARTY-NOTICES.txt` 包含实际构建的直接运行依赖的许可证与声明。Lite 优先使用发行版开发包，缺少 c-ares 静态库时使用依赖锁中的版本。macOS 使用系统 TLS 和 Homebrew。

当前源码归档覆盖 Aria2 及构建配方。公开分发静态二进制时，还需要按实际链接清单提供相应依赖的许可证、通知及适用的对应源码或可重链接材料。MinGW 的 GNU libiconv、工具链运行库和 Lite 的系统静态库需要分别核对。第三方下载链接用于追溯，项目仍需完成依赖材料的随包归档。
