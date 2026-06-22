# ffmeta — FFmpeg 链接示例

ffmeta 是一个简单的命令行工具，用于查看媒体文件信息。
演示如何通过 CMake + FindFFmpeg.cmake 链接预构建的 FFmpeg 库。

[English](README.md) | [简体中文](README_CN.md)

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

## 将 FFmpeg 集成到你的项目

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

### 按需链接各模块

```cmake
find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE
    FFmpeg::avformat
    FFmpeg::avcodec
    FFmpeg::avutil
)
```

## 运行示例

```bash
cmake -B build -DFFMPEG_ROOT=<绝对路径>
cmake --build build
build/Debug/ffmeta.exe input.mp4
```

示例支持三种链接方式，通过 `-DFFMPEG_LINK_MODE=full|demand|legacy` 切换
（默认 `full`）。

```bash
cmake -B build -DFFMPEG_ROOT=<路径> -DFFMPEG_LINK_MODE=demand
cmake --build build --config Debug
```

| 模式 | CMakeLists.txt 中的链接命令 | 用途 |
|------|----------------------------|------|
| `full` | `target_link_libraries(ffmeta PRIVATE FFmpeg::FFmpeg)` | 全量链接 |
| `demand` | `target_link_libraries(ffmeta PRIVATE FFmpeg::avformat …)` | 按需选择模块 |
| `legacy` | `target_link_libraries(ffmeta PRIVATE ${FFMPEG_LIBRARIES})` | 传统变量方式 |

## 向后兼容

旧名称 `FFMPEG::ffmpeg` / `FFMPEG::avformat` 仍可作为别名使用。

```cmake
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)   # 新名称（推荐）
target_link_libraries(myapp PRIVATE FFMPEG::ffmpeg)    # 旧名称（兼容）
```

## CMake Presets

```bash
cmake -B build --preset default -DFFMPEG_ROOT=<路径>
cmake --build build --preset default
```

| Preset | FFMPEG_LINK_MODE | 构建类型 |
|--------|-------------------|----------|
| `default` | `full` | Debug |
| `debug-demand` | `demand` | Debug |
| `debug-legacy` | `legacy` | Debug |
| `release` | `full` | Release |

## 文件说明

| 文件 | 用途 |
|------|------|
| `main.c` | ffmeta 源码 (libavutil + libavformat + libavcodec) |
| `CMakeLists.txt` | CMake 构建 |
| `CMakePresets.json` | CMake 预设 |
| `meson.build` | Meson 构建 |
| `Makefile` | GNU Make 构建 |
