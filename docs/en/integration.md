---
title: Integration
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
