# Integration

## Prerequisites

Download **Shared Binary** for the target application's architecture, [verify the ZIP](../guide/#verifying-downloads), and extract it, for example to `C:\Tools\ffmpeg`. The SDK root should contain `bin/`, `lib/`, `include/` and `share/ffmpeg/`. A complete static SDK is too large to distribute, so Static archives contain command-line tools only. For static linking, [build from source](../self-build/).

## Minimal version

Use CMake 3.21+ and MSVC. Create these two files in your project directory.

**CMakeLists.txt**

```cmake
cmake_minimum_required(VERSION 3.21)
project(myapp C)

list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
find_package(FFmpeg MODULE REQUIRED)

add_executable(myapp main.c)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
```

**main.c**

```c
#include <stdio.h>
#include <libavutil/avutil.h>

int main(void) {
    puts(av_version_info());
    return 0;
}
```

Configure, build and run in PowerShell (Visual Studio multi-config generator, x64):

```powershell
cmake -S . -B build -A x64 "-DFFMPEG_ROOT=C:/Tools/ffmpeg"
cmake --build build --config Release
$env:Path = "C:\Tools\ffmpeg\bin;$env:Path"
.\build\Release\myapp.exe
```

The program should print the FFmpeg version. For ARM64, x86 or ARM, select the matching generator platform (Win32 for x86). With Ninja or similar generators, use the matching MSVC toolchain environment and omit `-A`.

## With DLL deployment (Windows shared builds)

Append this to the CMakeLists.txt above. It copies matching DLLs after building, so you need not change PATH at runtime, and includes them on installation.

```cmake
add_custom_command(TARGET myapp POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_RUNTIME_DLLS:myapp>" "$<TARGET_FILE_DIR:myapp>"
    COMMAND_EXPAND_LISTS
)
install(TARGETS myapp RUNTIME DESTINATION bin)
install(FILES $<TARGET_RUNTIME_DLLS:myapp> DESTINATION bin)
```

```powershell
cmake --build build --config Release
cmake --install build --config Release --prefix dist
.\dist\bin\myapp.exe
```

Before distributing your application, read [Licenses and redistribution](../licenses/).

## Debug builds and symbols

1. Extract Debug from the same build batch, architecture, license and linkage over Shared Binary. An older complete Develop archive can be used directly instead.
2. Reconfigure and run `cmake --build build --config Debug`. If automatic deployment is enabled, run the application from the Debug output directory.
3. In Visual Studio, open Debug > Windows > Modules and verify the loaded DLLs and PDBs match.

The updated CMake module selects Debug libraries when a complete Debug library/DLL set is available; otherwise it uses Release libraries. Release PDBs are in `bin/` (when supplied); Debug DLLs and PDBs are in `debug/bin/`. Never mix libraries or symbols from unrelated builds.

## Other linking methods

To link only selected modules, replace the link command with:

```cmake
target_link_libraries(myapp PRIVATE
    FFmpeg::avformat FFmpeg::avcodec FFmpeg::avutil
)
```

Legacy projects can use `${FFMPEG_INCLUDE_DIRS}` and `${FFMPEG_LIBRARIES}`. Without CMake, add `include/` and `lib/` to your compiler/linker configuration, link the required import libraries, and deploy matching DLLs from `bin/`. Variable-based linking does not provide imported-target DLL discovery; deploy DLLs manually.

## How it works

`FFMPEG_ROOT` points to the SDK root. `CMAKE_MODULE_PATH` makes the supplied `FindFFmpeg.cmake` discoverable. It finds headers, import libraries and DLLs, creates imported targets, and selects libraries per configuration. `FFmpeg::FFmpeg` aggregates available modules; `TARGET_RUNTIME_DLLS` resolves DLLs from imported targets. Reconfigure after changing SDKs; older modules may require a fresh build directory.

## Available targets

| Target | Purpose |
|---|---|
| `FFmpeg::FFmpeg` | All available modules |
| `FFmpeg::avutil` | Common utilities |
| `FFmpeg::avcodec` | Codecs |
| `FFmpeg::avformat` | Muxing and demuxing |
| `FFmpeg::avfilter` | Filters |
| `FFmpeg::avdevice` | Device I/O |
| `FFmpeg::swresample` | Audio resampling |
| `FFmpeg::swscale` | Scaling and color conversion |

Legacy names such as `FFMPEG::ffmpeg` and `FFMPEG::avcodec` remain supported. Availability depends on version and build configuration.

## Available variables

| Variable | Description |
|---|---|
| `FFMPEG_FOUND` / `FFMPEG_VERSION` | Discovery result / version |
| `FFMPEG_INCLUDE_DIRS` | Header search paths |
| `FFMPEG_LIBRARY_DIRS` | Library search paths |
| `FFMPEG_LIBRARIES` / `FFMPEG_LIBRARY` | Library list |

Per-module variables use the prefix `FFMPEG_lib<name>_`, e.g. `FFMPEG_libavcodec_LIBRARY_RELEASE`. Suffixes include `FOUND`, `INCLUDE_DIRS`, `LIBRARY`, `LIBRARY_RELEASE`, `LIBRARY_DEBUG`, `VERSION`, `DLL_RELEASE`, `DLL_DEBUG` and `DEPS_LIBRARY`, depending on the module and build.

See the [repository examples](https://github.com/System233/ffmpeg-msvc-prebuilt/tree/main/examples) for a complete media information application.
