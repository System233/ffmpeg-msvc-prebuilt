# ffmeta - FFmpeg Linking Example

ffmeta is a simple CLI tool that prints media file container format
and stream information. It demonstrates how to link against a prebuilt
FFmpeg distribution using three different build systems.

[English](README.md) [简体中文](README_CN.md) 

## Usage

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

## Build

### Method 1: CMake + FindFFMPEG.cmake

```bash
cmake -B build -DFFMPEG_ROOT=<absolute_path_to_ffmpeg_prefix>
cmake --build build
```

`FindFFMPEG.cmake` is located under `FFMPEG_ROOT/share/ffmpeg/`.  
Generated from `scripts/cmake/FindFFMPEG.cmake.in`, it supports three
linking methods:

| Method          | Command                                                      | Description                                           |
| --------------- | ------------------------------------------------------------ | ----------------------------------------------------- |
| A (recommended) | `target_link_libraries(ffmeta PRIVATE FFMPEG::ffmpeg)`       | Umbrella target, includes all modules and system deps |
| B               | `target_link_libraries(ffmeta PRIVATE FFMPEG::avformat ...)` | Per-module linking                                    |
| C               | `target_link_libraries(ffmeta PRIVATE ${FFMPEG_LIBRARIES})`  | Legacy variable approach                              |

### Method 2: Meson + pkg-config

```bash
PKG_CONFIG_PATH=<ffmpeg_prefix>/lib/pkgconfig meson setup build
meson compile -C build
```

### Method 3: GNU Make + pkg-config

```bash
make PKG_CONFIG_PATH=<ffmpeg_prefix>/lib/pkgconfig
```

## Files

| File             | Purpose                                              |
| ---------------- | ---------------------------------------------------- |
| `main.c`         | ffmeta source (libavutil + libavformat + libavcodec) |
| `CMakeLists.txt` | CMake build                                          |
| `meson.build`    | Meson build                                          |
| `Makefile`       | GNU Make build                                       |
