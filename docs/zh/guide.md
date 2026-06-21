---
title: 使用指南
---

# 使用指南

## 快速开始

1. 打开 [GitHub Pages 站点](https://system233.github.io/ffmpeg-msvc-prebuilt/) 或 [Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
2. 选择合适的变体：

   | 选项 | 说明 |
   |---|---|
   | **版本** | 稳定版 (7.x, 8.x) 或 **Master**（每周最新构建） |
   | **许可证** | **GPL**（包含 x264、x265）/ **LGPL**（更宽松） |
   | **链接方式** | **Shared**（DLL，可开发可运行）/ **Static**（单 exe，便携） |
   | **架构** | x64、x86、ARM64、ARM |

3. 下载 `.zip` 压缩包，解压即可使用

不确定如何选择？推荐 **稳定版 + Shared + GPL**，覆盖大部分使用场景。

## 理解构建产物

每版本有 **16 个变体**（4 架构 × 2 许可证 × 2 链接方式）。
Shared 变体额外包含一个 **develop** 包（含调试符号）。

### 文件命名

```
ffmpeg-8.1.1-r2_x64-windows-shared-gpl.zip         ← binary（可运行 + 开发文件）
ffmpeg-8.1.1-r2_x64-windows-shared-gpl-develop.zip  ← develop（含调试符号）
         ↑       ↑           ↑      ↑
     版本号    triplet    链接方式  许可证
```

- **版本号**: FFmpeg 发布号（如 `8.1.1`）或 Master 的 git describe
- **修订号** (`-r2`): 同一版本重新构建的次数
- **Triplet**: `{架构}-windows` — `x64`、`x86`、`arm64`、`arm`
- **链接方式**: `shared`（DLL）或 `static`（独立 exe）
- **许可证**: `gpl` 或 `lgpl`

### Binary 与 Develop 的区别（仅 shared）

| | Binary | Develop |
|---|---|---|
| ffmpeg.exe / ffplay.exe / ffprobe.exe | ✅ | ✅ |
| 头文件 (`.h`) | ✅ | ✅ |
| 导入库 (`.lib`) + DLL | ✅ | ✅ |
| pkg-config (`.pc`) + CMake 模块 | ✅ | ✅ |
| PDB 调试符号 | ❌ | ✅ |
| 调试库（`debug/lib/`） | ❌ | ✅ |
| 压缩包体积 | 较小 | 较大 |

### 如何选择？

| 你的需求 | 下载 |
|---|---|
| 运行 FFmpeg 命令行 | **Static Binary**（单文件）或 **Shared Binary** |
| 开发自己的 FFmpeg 应用 | **Shared Binary**（头文件 + 库） |
| 调试 FFmpeg 相关应用 | **Shared Develop**（含 PDB） |
| 单个 exe，无需 DLL | **Static Binary** |

**Static** 变体仅包含可执行文件 — 没有头文件和导入库。

## 包含内容

### Binary（所有链接方式）

- **命令行工具**: `ffmpeg.exe`、`ffplay.exe`、`ffprobe.exe`
- **开发文件**（仅 shared）：头文件 (`.h`)、导入库 (`.lib`)、DLL
- **集成支持**（仅 shared）：pkg-config 文件 (`.pc`)、CMake `FindFFMPEG.cmake`
- **元数据**: `BUILD_INFO`、`CONTROL`、`LICENSE.txt`
- 所有依赖已静态链接或打包 —— **零运行时 DLL 依赖**

### Develop（仅 shared，在 Binary 基础上增加）

- **PDB 符号文件**（所有 exe 和 DLL）
- **调试库**（位于 `debug/lib/`）

### Static

- 仅独立可执行文件 —— 运行时无需任何外部 DLL
