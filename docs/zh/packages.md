# 构建产物

## 二进制与调试库

| 文件 | 共享库二进制 | 共享库调试库 | 静态库二进制 |
|---|---|---|---|
| FFmpeg 命令行工具 | 有 | 无 | 有 |
| 头文件、导入库、DLL | 有 | 仅 Debug 库和 DLL | 无 SDK |
| CMake、pkg-config 集成 | 有 | 无 | 无 |
| PDB 调试符号 | — | 有（以实际归档为准） | — |

共享库 SDK 用于动态链接。完整静态链接 SDK 包含大量第三方静态库，体积过大，因此静态库构建仅分发独立命令行工具，不提供 SDK；需要静态链接开发时请[自行构建](../self-build/)。静态库构建的命令行工具无需独立 FFmpeg DLL。

### 调试库（仅共享库，依赖二进制）

将调试库覆盖解压至同一批次、架构、许可证和链接方式的共享库二进制目录。旧版 Develop 为完整独立包，无需再叠加 Binary。

- `bin/`：Release DLL；匹配的 Release PDB 在调试库中提供。
- `debug/lib/`：Debug 导入库。
- `debug/bin/`：Debug DLL 和匹配 PDB。
- CLI EXE PDB 仅在构建生成且匹配时提供。

参见[调试构建与符号](../integration/#调试构建与符号)。

## 目录结构

| 路径 | 内容 |
|---|---|
| `bin/` | 共享库命令行工具与 DLL |
| `include/` | 共享库 SDK 头文件 |
| `lib/` | 共享库 导入库及 pkg-config 文件 |
| `share/ffmpeg/` | CMake 模块及合规文件 |
| `debug/` | 可选调试库 |
| `LICENSE.txt` | 主许可证 |

静态库归档通常在根目录提供命令行工具。历史归档的实际结构可能不同。

## 文件命名

```text
ffmpeg-9.1_x64-windows-static-lgpl-261125.zip
ffmpeg-9.1_arm64-windows-shared-gpl-261125.zip
ffmpeg-9.1_arm64-windows-shared-gpl-debug-261125.zip
ffmpeg-master_x64-windows-static-gpl-261125.zip
```

以上为命名格式示例。日期使用 UTC YYMMDD；同日发布批次的 Release Tag 可追加 R2、R3 等。公开文件名不包含 ABI 或打包格式编号。复用的归档保留原始文件名和 SHA-256；历史归档可能采用修订号命名。

标准矩阵包含 16 个构建变体（4 架构 × 2 许可证 × 2 链接方式），完整发布包含 24 个 ZIP（8 静态库、8 共享库、8 调试库）。实际可用构建以下载页为准。

## 相关文档

[使用指南](../guide/) · [开发集成](../integration/) · [许可证与再分发](../licenses/)
