---
title: 开发集成
description: 通过 FindFFmpeg.cmake 将预构建的 FFmpeg MSVC 二进制文件集成到你的 CMake 项目 — 目标、变量和代码示例。
---

# 将 FFmpeg 集成到你的 CMake 项目

本文档说明如何通过 `FindFFmpeg.cmake` 将预构建的 FFmpeg 共享库
（MSVC）链接到你自己的 CMake 项目。

## 前置条件

下载 **shared** 类型的预构建 FFmpeg 压缩包（binary 或 develop 均可），
可从 [Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
或 [GitHub Pages](https://system233.github.io/ffmpeg-msvc-prebuilt/) 获取。

解压后得到包含 `bin/`、`lib/`、`include/`、`share/ffmpeg/` 的目录，
该目录路径即为 **`FFMPEG_ROOT`**。

> **注意**: Static 变体不包含头文件和库，无法用于开发。请使用 shared 变体。

## 工作原理

```
用户传入 FFMPEG_ROOT
         │
         ▼
CMakeLists.txt 追加 CMAKE_MODULE_PATH
  → list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
         │
         ▼
find_package(FFmpeg MODULE) 加载 FindFFmpeg.cmake
  → 扫描 FFMPEG_ROOT/include 和 FFMPEG_ROOT/lib
  → 结果缓存到 CMakeCache.txt（下次不重复扫描）
  → Windows 共享构建下自动检测 DLL
  → 创建导入目标，正确设置路径
         │
         ▼
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
  → CMake 自动处理：头文件路径、导入库、DLL 路径、Debug/Release 切换
```

## 快速开始代码片段

将以下代码复制到你的 `CMakeLists.txt` 中，
配置时传入 `-DFFMPEG_ROOT=<绝对路径>`。

### 最小版本

```cmake
cmake_minimum_required(VERSION 3.21)
project(myapp C)

# ---- 必需：指向解压后的 FFmpeg 目录 ----
if(NOT DEFINED FFMPEG_ROOT)
    message(FATAL_ERROR "\n  请在 cmake 命令中传入 -DFFMPEG_ROOT=<绝对路径>\n")
endif()
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")

find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
```

### 带 DLL 自动部署（Windows 共享构建）

构建时和安装时自动复制 DLL。

```cmake
cmake_minimum_required(VERSION 3.21)
project(myapp C)

if(NOT DEFINED FFMPEG_ROOT)
    message(FATAL_ERROR "\n  请在 cmake 命令中传入 -DFFMPEG_ROOT=<绝对路径>\n")
endif()
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")

find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)

# 构建后自动复制 DLL 到输出目录
add_custom_command(TARGET myapp POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_RUNTIME_DLLS:myapp>" "$<TARGET_FILE_DIR:myapp>"
    COMMAND_EXPAND_LISTS
)

# 安装可执行文件 + DLL
install(TARGETS myapp RUNTIME DESTINATION bin)
install(FILES $<TARGET_RUNTIME_DLLS:myapp> DESTINATION bin)
```

### 传统变量方式

适用于无法使用 CMake 目标的旧项目。

```cmake
find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_include_directories(myapp PRIVATE ${FFMPEG_INCLUDE_DIRS})
target_link_libraries(myapp PRIVATE ${FFMPEG_LIBRARIES})
```

### 按需链接各模块（不使用 umbrella）

```cmake
find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE
    FFmpeg::avformat
    FFmpeg::avcodec
    FFmpeg::avutil
)
```

## 可用目标

每个 FFmpeg 模块都导出为一个 CMake 导入目标：

| 目标 | 说明 |
|---|---|
| `FFmpeg::FFmpeg` | 伞目标 — 链接所有模块并设置头文件路径 |
| `FFMPEG::ffmpeg` | `FFmpeg::FFmpeg` 的别名（旧名称） |
| `FFmpeg::avutil` | libavutil — 通用工具 |
| `FFmpeg::avcodec` | libavcodec — 音视频编解码器 |
| `FFmpeg::avformat` | libavformat — 封装/解封装器 |
| `FFmpeg::avfilter` | libavfilter — 滤镜图 |
| `FFmpeg::avdevice` | libavdevice — 设备输入输出 |
| `FFmpeg::swresample` | libswresample — 音频重采样 |
| `FFmpeg::swscale` | libswscale — 图像缩放/色彩转换 |

每个模块目标也提供旧 `FFMPEG::` 命名空间别名（如 `FFMPEG::avcodec`）。

## 可用变量

### 全局变量

| 变量 | 说明 |
|---|---|
| `FFMPEG_FOUND` | 是否找到 FFmpeg |
| `FFMPEG_VERSION` | FFmpeg 版本号 |
| `FFMPEG_INCLUDE_DIRS` | 头文件搜索路径 |
| `FFMPEG_LIBRARY_DIRS` | 库文件搜索路径 |
| `FFMPEG_LIBRARIES` | 完整库文件列表 |
| `FFMPEG_LIBRARY` | 等同于 `FFMPEG_LIBRARIES` |

### 模块级变量

对于每个模块 `<name>` 属于 `{avutil, avcodec, avformat, avfilter, avdevice, swresample, swscale}`：

| 变量 | 说明 |
|---|---|
| `FFMPEG_lib<name>_FOUND` | 是否找到该模块 |
| `FFMPEG_lib<name>_INCLUDE_DIRS` | 模块专用头文件目录 |
| `FFMPEG_lib<name>_LIBRARY` | 模块库路径（自动识别 Debug/Release） |
| `FFMPEG_lib<name>_LIBRARY_RELEASE` | Release 库路径 |
| `FFMPEG_lib<name>_LIBRARY_DEBUG` | Debug 库路径 |
| `FFMPEG_lib<name>_VERSION` | 模块版本（如 `61.19.100`） |
| `FFMPEG_lib<name>_DLL_RELEASE` | Release DLL 路径（仅 Windows 共享库） |
| `FFMPEG_lib<name>_DLL_DEBUG` | Debug DLL 路径（仅 Windows 共享库） |
| `FFMPEG_lib<name>_DEPS_LIBRARY` | 该模块的外部依赖库 |

## 兼容性

旧名称 `FFMPEG::ffmpeg` / `FFMPEG::avformat` 等仍可作为别名使用：

```cmake
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)   # 新名称（推荐）
target_link_libraries(myapp PRIVATE FFMPEG::ffmpeg)    # 旧名称（兼容）
```

## 示例：ffmeta

一个完整的可运行示例位于仓库的
[`examples/`](https://github.com/System233/ffmpeg-msvc-prebuilt/tree/main/examples)
目录。它演示了所有三种链接方式，并包含 `CMakePresets.json` 用于快速配置。

构建说明请参见
[`examples/README_CN.md`](https://github.com/System233/ffmpeg-msvc-prebuilt/tree/main/examples)。
