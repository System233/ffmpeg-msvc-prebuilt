# ffmeta — FFmpeg 链接示例

ffmeta 是一个简单的命令行工具，用于查看媒体文件信息。
演示通过 CMake Config 或 Find Module 链接预构建的 FFmpeg 库。

[English](README.md) | [简体中文](README_CN.md)

## 前置条件

下载 **shared** 类型的预构建 FFmpeg 压缩包（Binary；可按需覆盖解压对应 Debug Add-on），
可从 [Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
或 [GitHub Pages](https://system233.github.io/ffmpeg-msvc-prebuilt/) 获取。

解压后得到包含 `bin/`、`lib/`、`include/`、`share/ffmpeg/` 的目录，
使用该路径作为 `CMAKE_PREFIX_PATH`（历史 SDK 使用 `FFMPEG_ROOT`）。

> **注意**: Static 变体不包含头文件和库，无法用于开发。请使用 shared 变体。
> Shared SDK 仅支持动态链接，导入库不是静态库；`pkg-config --static` 不提供静态 SDK。

## 工作原理

CMake 通过 `CMAKE_PREFIX_PATH` 发现 SDK 并加载 `FFmpegConfig.cmake`。共享实现创建导入目标、传递依赖并选择 Debug 或 Release 文件。历史 SDK 仍支持原有 Find Module。

## 将 FFmpeg 集成到你的项目

将以下代码复制到你的 `CMakeLists.txt` 中，
配置时传入 `-DCMAKE_PREFIX_PATH=<绝对路径>`。

旧版 SDK 若未提供 Config 接口，请传入 `-DFFMPEG_ROOT=<绝对路径>`，并将 Config 调用替换为：

```cmake
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
find_package(FFmpeg 5.0 MODULE REQUIRED)
```

### 最小版本

```cmake
cmake_minimum_required(VERSION 3.21)
project(myapp C)

find_package(FFmpeg 5.0 CONFIG REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
```

### 带 DLL 自动部署（Windows 共享构建）

构建时和安装时自动复制 DLL。

```cmake
cmake_minimum_required(VERSION 3.21)
project(myapp C)

find_package(FFmpeg 5.0 CONFIG REQUIRED)

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
find_package(FFmpeg 5.0 CONFIG REQUIRED)

add_executable(myapp main.c)
target_include_directories(myapp PRIVATE ${FFMPEG_INCLUDE_DIRS})
target_link_libraries(myapp PRIVATE ${FFMPEG_LIBRARIES})
```

### 按需链接各模块

```cmake
find_package(FFmpeg 5.0 CONFIG REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE
    FFmpeg::avformat
    FFmpeg::avcodec
    FFmpeg::avutil
)
```

## 运行示例

```bash
cmake -B build -DCMAKE_PREFIX_PATH=<绝对路径>
cmake --build build
build/Debug/ffmeta.exe input.mp4
```

示例支持三种链接方式，通过 `-DFFMPEG_LINK_MODE=full|demand|legacy` 切换
（默认 `full`）。

```bash
cmake -B build -DCMAKE_PREFIX_PATH=<路径> -DFFMPEG_LINK_MODE=demand
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
cmake -B build --preset default -DCMAKE_PREFIX_PATH=<路径>
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
