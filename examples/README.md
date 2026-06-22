# ffmeta — FFmpeg Linking Example

ffmeta is a simple CLI tool that prints media file information.
It demonstrates how to link against a prebuilt FFmpeg distribution
using CMake and FindFFmpeg.cmake.

[English](README.md) | [简体中文](README_CN.md)

## Prerequisites

Download a **shared** prebuilt FFmpeg archive (binary or develop) from
the [releases page](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
or [GitHub Pages](https://system233.github.io/ffmpeg-msvc-prebuilt/).

Extract the `.zip` — the resulting directory contains `bin/`, `lib/`,
`include/`, and `share/ffmpeg/`. This path is your **`FFMPEG_ROOT`**.

> **Note**: The static variant does not include headers or libraries
> and cannot be used for development. Use a shared variant instead.

## How It Works

```
User passes FFMPEG_ROOT
         │
         ▼
CMakeLists.txt appends to CMAKE_MODULE_PATH
  → list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
         │
         ▼
find_package(FFmpeg MODULE) loads FindFFmpeg.cmake
  → scans FFMPEG_ROOT/include and FFMPEG_ROOT/lib
  → caches results (re-configure skips scan)
  → detects DLLs on Windows shared builds
  → creates imported targets with proper locations
         │
         ▼
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
  → CMake wires up include dirs, import libs, DLL paths,
    and per-config (Debug/Release) switching
```

## Integrating FFmpeg into Your Project

Copy the following into your own `CMakeLists.txt` and
pass `-DFFMPEG_ROOT=<absolute_path>` at configure time.

### Minimal version

```cmake
cmake_minimum_required(VERSION 3.21)
project(myapp C)

# ---- Required: point to the extracted FFmpeg archive ----
if(NOT DEFINED FFMPEG_ROOT)
    message(FATAL_ERROR "\n  Pass -DFFMPEG_ROOT=<absolute_path> to cmake\n")
endif()
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")

find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
```

### With DLL deployment (Windows shared builds)

Adds automatic DLL copying at build time and install time.

```cmake
cmake_minimum_required(VERSION 3.21)
project(myapp C)

if(NOT DEFINED FFMPEG_ROOT)
    message(FATAL_ERROR "\n  Pass -DFFMPEG_ROOT=<absolute_path> to cmake\n")
endif()
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")

find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)

# Copy DLLs to the build output directory
add_custom_command(TARGET myapp POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_RUNTIME_DLLS:myapp>" "$<TARGET_FILE_DIR:myapp>"
    COMMAND_EXPAND_LISTS
)

# Install executable + DLLs
install(TARGETS myapp RUNTIME DESTINATION bin)
install(FILES $<TARGET_RUNTIME_DLLS:myapp> DESTINATION bin)
```

### Legacy variable approach

If you cannot use CMake targets.

```cmake
find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_include_directories(myapp PRIVATE ${FFMPEG_INCLUDE_DIRS})
target_link_libraries(myapp PRIVATE ${FFMPEG_LIBRARIES})
```

### Linking individual modules (without umbrella)

```cmake
find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE
    FFmpeg::avformat
    FFmpeg::avcodec
    FFmpeg::avutil
)
```

## Running the ffmeta Example

```bash
cmake -B build -DFFMPEG_ROOT=<absolute_path_to_ffmpeg_prefix>
cmake --build build
build/Debug/ffmeta.exe input.mp4
```

The example supports three linking methods controlled by
`-DFFMPEG_LINK_MODE=full|demand|legacy` (default: `full`).

```bash
cmake -B build -DFFMPEG_ROOT=<path> -DFFMPEG_LINK_MODE=demand
cmake --build build --config Debug
```

| Mode | Link command in CMakeLists.txt | Use case |
|------|-------------------------------|----------|
| `full` | `target_link_libraries(ffmeta PRIVATE FFmpeg::FFmpeg)` | All modules at once |
| `demand` | `target_link_libraries(ffmeta PRIVATE FFmpeg::avformat …)` | Select specific modules |
| `legacy` | `target_link_libraries(ffmeta PRIVATE ${FFMPEG_LIBRARIES})` | Variable‑based fallback |

## Backward Compatibility

Old `FFMPEG::ffmpeg` / `FFMPEG::avformat` names are kept as aliases.

```cmake
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)   # new (recommended)
target_link_libraries(myapp PRIVATE FFMPEG::ffmpeg)    # old (compat)
```

## CMake Presets

```bash
cmake -B build --preset default -DFFMPEG_ROOT=<path>
cmake --build build --preset default
```

| Preset | FFMPEG_LINK_MODE | Build type |
|--------|-------------------|------------|
| `default` | `full` | Debug |
| `debug-demand` | `demand` | Debug |
| `debug-legacy` | `legacy` | Debug |
| `release` | `full` | Release |

## Files

| File | Purpose |
|------|---------|
| `main.c` | ffmeta source (libavutil + libavformat + libavcodec) |
| `CMakeLists.txt` | CMake build |
| `CMakePresets.json` | CMake presets |
| `meson.build` | Meson build |
| `Makefile` | GNU Make build |
