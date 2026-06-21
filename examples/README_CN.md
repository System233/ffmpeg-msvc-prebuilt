# ffmeta — FFmpeg 链接示例

ffmeta 是一个简单的命令行工具，用于查看媒体文件的容器格式和流信息。  
它演示了如何通过三种构建系统正确链接预构建的 FFmpeg 库。

[English](README.md) | [简体中文](README_CN.md)

## 前置条件

下载 **shared** 类型的预构建 FFmpeg 压缩包（binary 或 develop 均可），
可从 [Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
或 [GitHub Pages](https://system233.github.io/ffmpeg-msvc-prebuilt/) 获取。

解压后得到包含 `bin/`、`lib/`、`include/`、`share/ffmpeg/` 的目录，
该目录路径即为 `FFMPEG_ROOT`。

> **注意**: Static 变体不包含头文件和库，无法用于开发。请使用 shared 变体。

## 功能

```
$ ffmeta input.mp4
=== input.mp4 ===
  Format: QuickTime / MOV (mov,mp4,m4a,3gp,3g2,mj2)
  Duration: 00:02:33.45
  Bitrate: 1256 kb/s
  Streams: 2
  Stream #0: Video h264 (High), yuv420p, 1920x1080, 1200 kb/s
  Stream #1: Audio aac (LC), 48000 Hz, 2 ch (fltp), 128 kb/s
    language: eng
  major_brand: isom
  encoder: Lavf60.0.100
```

## 构建

### 方式 1: CMake + FindFFMPEG.cmake

```bash
cmake -B build -DFFMPEG_ROOT=<ffmpeg_prefix绝对路径>
cmake --build build
```

`FindFFMPEG.cmake` 会在 `FFMPEG_ROOT/share/ffmpeg/` 下查找。  
该文件由 `scripts/cmake/FindFFMPEG.cmake.in` 生成，支持三种链接方式：

| 方式     | 命令                                                         | 说明                                      |
| -------- | ------------------------------------------------------------ | ----------------------------------------- |
| A (推荐) | `target_link_libraries(ffmeta PRIVATE FFMPEG::ffmpeg)`       | umbrella 目标，自动包含所有模块和系统依赖 |
| B        | `target_link_libraries(ffmeta PRIVATE FFMPEG::avformat ...)` | 按需链接各模块                            |
| C        | `target_link_libraries(ffmeta PRIVATE ${FFMPEG_LIBRARIES})`  | 传统变量方式                              |

### 方式 2: Meson + pkg-config

```bash
PKG_CONFIG_PATH=<ffmpeg_prefix>/lib/pkgconfig meson setup build
meson compile -C build
```

### 方式 3: GNU Make + pkg-config

```bash
make PKG_CONFIG_PATH=<ffmpeg_prefix>/lib/pkgconfig
```

## 文件说明

| 文件             | 用途                                               |
| ---------------- | -------------------------------------------------- |
| `main.c`         | ffmeta 源码 (libavutil + libavformat + libavcodec) |
| `CMakeLists.txt` | CMake 构建                                         |
| `meson.build`    | Meson 构建                                         |
| `Makefile`       | GNU Make 构建                                      |
