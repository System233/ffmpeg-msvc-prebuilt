<div align="center">

[English](README.md) | [简体中文](README_CN.md)

[![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-浏览全部构建结果-2ea44f?style=for-the-badge&logo=github)](https://system233.github.io/ffmpeg-msvc-prebuilt/)

# FFmpeg MSVC 预构建

使用 MSVC 编译的 Windows FFmpeg 预构建二进制包。
解压即用，无需配置环境。

[![Build](https://img.shields.io/github/actions/workflow/status/System233/ffmpeg-msvc-prebuilt/build-release.yml?label=Build&logo=github)](https://github.com/System233/ffmpeg-msvc-prebuilt/actions/workflows/build-release.yml)
[![Master](https://img.shields.io/github/actions/workflow/status/System233/ffmpeg-msvc-prebuilt/master-build.yml?label=Master&logo=github)](https://github.com/System233/ffmpeg-msvc-prebuilt/actions/workflows/master-build.yml)
[![Pages](https://img.shields.io/github/actions/workflow/status/System233/ffmpeg-msvc-prebuilt/pages.yml?branch=web&label=Pages&logo=github)](https://github.com/System233/ffmpeg-msvc-prebuilt/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/v/release/System233/ffmpeg-msvc-prebuilt?display_name=tag&label=Release)](https://github.com/System233/ffmpeg-msvc-prebuilt/releases/latest)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20GPL%20%2F%20LGPL-blue)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/System233/ffmpeg-msvc-prebuilt)](https://github.com/System233/ffmpeg-msvc-prebuilt/commits/main)

</div>

---

## 🚀 浏览预构建二进制文件

**[https://system233.github.io/ffmpeg-msvc-prebuilt/](https://system233.github.io/ffmpeg-msvc-prebuilt/)**

按版本、架构、许可证搜索所有构建产物，一键下载。无需命令行，无需 GitHub 账号。

也可直接访问 **[GitHub Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)** 下载。

---

## 快速开始

1. 打开 [GitHub Pages 站点](https://system233.github.io/ffmpeg-msvc-prebuilt/) 或 [Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
2. 选择合适的变体：

   | 选项         | 说明                                                        |
   | ------------ | ----------------------------------------------------------- |
   | **版本**     | 稳定版 (7.x, 8.x) 或 **Master**（每周最新构建）             |
   | **许可证**   | **GPL**（包含 x264、x265）/ **LGPL**（更宽松）              |
   | **链接方式** | **Shared**（DLL，可开发可运行）/ **Static**（单 exe，便携） |
   | **架构**     | x64、x86、ARM64、ARM                                        |

3. 下载 `.zip` 压缩包，解压即可使用

不确定如何选择？推荐 **稳定版 + Shared + GPL**，覆盖大部分使用场景。

---

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

|                                       | Binary | Develop |
| ------------------------------------- | ------ | ------- |
| ffmpeg.exe / ffplay.exe / ffprobe.exe | ✅      | ✅       |
| 头文件 (`.h`)                         | ✅      | ✅       |
| 导入库 (`.lib`) + DLL                 | ✅      | ✅       |
| pkg-config (`.pc`) + CMake 模块       | ✅      | ✅       |
| PDB 调试符号                          | ❌      | ✅       |
| 调试库（`debug/lib/`）                | ❌      | ✅       |
| 压缩包体积                            | 较小   | 较大    |

### 如何选择？

| 你的需求               | 下载                                            |
| ---------------------- | ----------------------------------------------- |
| 运行 FFmpeg 命令行     | **Static Binary**（单文件）或 **Shared Binary** |
| 开发自己的 FFmpeg 应用 | **Shared Binary**（头文件 + 库）                |
| 调试 FFmpeg 相关应用   | **Shared Develop**（含 PDB）                    |
| 单个 exe，无需 DLL     | **Static Binary**                               |

**Static** 变体仅包含可执行文件 — 没有头文件和导入库。

---

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

---

## 开发集成示例 — ffmeta

[`examples/`](./examples/) 目录包含 `ffmeta` 命令行媒体元数据查看工具，演示三种链接 FFmpeg 库的方式。

下载 **shared binary** 或 **shared develop** 压缩包，解压后指向其路径即可：

```bash
# 先解压，再构建
cmake -B build -DFFMPEG_ROOT=C:/path/to/extracted_prefix
cmake --build build
```

详见 [`examples/README_CN.md`](./examples/README_CN.md) 中的 CMake、Meson 和 GNU Make 说明。

---

## 项目特点

- **MSVC 编译** — 原生 Windows 兼容，性能出色
- **多架构支持** — x64、x86、ARM、ARM64
- **每周 Master 构建** — 追踪 FFmpeg 最新开发分支
- **自动上游检测** — 新版本发布后自动检测并构建
- **LTS 长期维护** — 稳定版持续支持

---

## 许可证

- 仓库脚本和配置：**MIT License**
- FFmpeg 及其依赖：**GPL** / **LGPL**（按所选变体）

---

<div align="center">

有问题？[提交 Issue](https://github.com/System233/ffmpeg-msvc-prebuilt/issues)

</div>
