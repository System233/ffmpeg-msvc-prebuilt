---
title: Integration
description: Integrate prebuilt FFmpeg MSVC binaries into your CMake project using FindFFmpeg.cmake — targets, variables, and code snippets.
---

# Integrating FFmpeg into Your CMake Project

This guide explains how to link a prebuilt FFmpeg distribution
(shared, MSVC) into your own CMake project using `FindFFmpeg.cmake`.

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

## Quick Start Snippets

Copy one of the following into your own `CMakeLists.txt` and
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

## Available Targets

Each FFmpeg module is exposed as a CMake imported target:

| Target | Description |
|---|---|
| `FFmpeg::FFmpeg` | Umbrella target — links all modules and sets include dirs |
| `FFMPEG::ffmpeg` | Alias for `FFmpeg::FFmpeg` (legacy) |
| `FFmpeg::avutil` | libavutil — common utilities |
| `FFmpeg::avcodec` | libavcodec — audio/video codecs |
| `FFmpeg::avformat` | libavformat — muxers/demuxers |
| `FFmpeg::avfilter` | libavfilter — filter graphs |
| `FFmpeg::avdevice` | libavdevice — device I/O |
| `FFmpeg::swresample` | libswresample — audio resampling |
| `FFmpeg::swscale` | libswscale — image scaling / color conversion |

Each module target is also available under the legacy `FFMPEG::` namespace
(e.g. `FFMPEG::avcodec`).

## Available Variables

### Global variables

| Variable | Description |
|---|---|
| `FFMPEG_FOUND` | True if FFmpeg was found |
| `FFMPEG_VERSION` | FFmpeg version string |
| `FFMPEG_INCLUDE_DIRS` | Header file search paths |
| `FFMPEG_LIBRARY_DIRS` | Library search paths |
| `FFMPEG_LIBRARIES` | Full list of library paths |
| `FFMPEG_LIBRARY` | Same as `FFMPEG_LIBRARIES` |

### Per-module variables

For each module `<name>` in `{avutil, avcodec, avformat, avfilter, avdevice, swresample, swscale}`:

| Variable | Description |
|---|---|
| `FFMPEG_lib<name>_FOUND` | Whether this module was found |
| `FFMPEG_lib<name>_INCLUDE_DIRS` | Module-specific include dirs |
| `FFMPEG_lib<name>_LIBRARY` | Module library path (Debug/Release aware) |
| `FFMPEG_lib<name>_LIBRARY_RELEASE` | Release library path |
| `FFMPEG_lib<name>_LIBRARY_DEBUG` | Debug library path |
| `FFMPEG_lib<name>_VERSION` | Module version (e.g. `61.19.100`) |
| `FFMPEG_lib<name>_DLL_RELEASE` | Release DLL path (Windows shared only) |
| `FFMPEG_lib<name>_DLL_DEBUG` | Debug DLL path (Windows shared only) |
| `FFMPEG_lib<name>_DEPS_LIBRARY` | External dependency libraries for this module |

## Compatibility

The old `FFMPEG::ffmpeg` / `FFMPEG::avformat` names are kept as
aliases. Both naming schemes work:

```cmake
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)   # new (recommended)
target_link_libraries(myapp PRIVATE FFMPEG::ffmpeg)    # old (compat)
```

## Example: ffmeta

A complete runnable example is available under
[`examples/`](https://github.com/System233/ffmpeg-msvc-prebuilt/tree/main/examples)
in the repository. It demonstrates all three linking methods and
includes a CMakePresets.json for quick configuration.

See [`examples/README.md`](https://github.com/System233/ffmpeg-msvc-prebuilt/tree/main/examples)
for build instructions.
