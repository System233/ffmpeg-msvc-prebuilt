# FFmpeg CMake ExternalProject Build

使用 CMake ExternalProject_Add 构建 FFmpeg 及其 16 个依赖。通过 `ToolchainMSVC.cmake` 统一管理 MSVC 编译工具链，通过 `DepPackage.cmake` 宏系统实现 NPM 风格的依赖注册与版本管理。支持 `CMakePresets.json` 预设构建方案。

## 依赖 (16/16)

| 依赖 | 版本 | 构建系统 | 许可证 | FFmpeg 标志 |
|------|------|---------|--------|------------|
| zlib | 1.3.1 | CMake | zlib | `--enable-zlib` |
| x264 | master | autotools | GPL | `--enable-libx264` |
| x265 | 4.1 | CMake | GPL | `--enable-libx265` |
| fribidi | 1.0.16 | autotools | LGPL | `--enable-libfribidi` |
| freetype | 2.13.3 | CMake | FreeType | `--enable-libfreetype` |
| harfbuzz | 10.1.0 | CMake | MIT | `--enable-libharfbuzz` |
| libass | 0.17.3 | autotools | ISC | `--enable-libass` |
| libvpx | 1.15.0 | autotools | BSD | `--enable-libvpx` |
| libwebp | 1.5.0 | CMake | BSD | `--enable-libwebp` |
| dav1d | 1.5.1 | meson | BSD | `--enable-libdav1d` |
| opus | 1.5.2 | CMake | BSD | `--enable-libopus` |
| soxr | 0.1.3 | CMake | LGPL | `--enable-libsoxr` |
| SDL2 | 2.30.11 | CMake | zlib | `--enable-sdl2` |
| libjxl | 0.11.1 | CMake | BSD | `--enable-libjxl` |
| nv-codec-headers | 12.2.72.0 | autotools | MIT | (仅头文件) |

### 内部传递依赖

| 依赖 | 被要求者 | 说明 |
|------|---------|------|
| openexr 3.3.2 | libjxl | 已禁用（`JPEGXL_ENABLE_OPENEXR=OFF`），不构建 |
| highway 1.2.0 | libjxl | SIMD 加速库 |
| brotli 1.1.0 | libjxl | 无损压缩 |
| lcms2 2.16 | libjxl | 色彩管理 |
| GNU Automake compile | libvpx | MSVC 编译包装器 |

## 构建系统架构

```
CMakeLists.txt
│
├─【Phase 1: 注册】include 所有 External_*.cmake
│    └─ dep_package() / dep_package_version() → GLOBAL PROPERTY 注册表
│
├─【Phase 2: 族加载】include families/*.cmake
│    └─ ffmpeg_family(NAME 7.x VERSION_RANGE ">=7.0 <8.0" DEPS ...)
│
├─【Phase 3: 解析】DepResolver.cmake
│    ├─ 匹配 FFMPEG_VERSION → family → URL/补丁/DEFAULT_DEPS
│    ├─ 传递依赖闭合 (DFS 递归)
│    ├─ 许可证检查 (LICENSE=lgpl → 排除 GPL dep)
│    ├─ 版本约束检查 (dep_constraint)
│    └─ 输出: RESOLVED_DEPS, FFMPEG_ASM_DEPENDS, FFMPEG_ASM_FLAGS
│
├─【Phase 4: 构建】BuildAssembly.cmake
│    └─ foreach dep: cmake_language(CALL build_${dep})
│
└─【Phase 5: 发行说明】ReleaseNote.cmake
     └─ add_custom_target(release_note)
```

## 项目结构

```
ffmpeg-cmake-build/
├── CMakeLists.txt                    # 5-Phase 主入口
├── CMakePresets.json                 # 构建方案预设
├── README.md
├── AGENTS.md
├── .gitignore
├── cmake/
│   ├── ToolchainMSVC.cmake           # MSVC 工具链 + ENV 变量
│   ├── BootstrapMSYS2.cmake          # MSYS2 路径检测
│   ├── DepPackage.cmake              # dep_package / ffmpeg_family 宏
│   ├── DepResolver.cmake             # 版本匹配 + 依赖解析
│   ├── BuildAssembly.cmake           # 构建调度
│   ├── ReleaseNote.cmake             # 发行说明生成
│   ├── compile                       # GNU Automake MSVC 包装器 (libvpx)
│   ├── External_Zlib.cmake
│   ├── External_X264.cmake
│   ├── External_X265.cmake
│   ├── External_Fribidi.cmake
│   ├── External_Freetype.cmake
│   ├── External_Harfbuzz.cmake
│   ├── External_Libass.cmake
│   ├── External_Libvpx.cmake
│   ├── External_Libwebp.cmake
│   ├── External_Dav1d.cmake
│   ├── External_Opus.cmake
│   ├── External_Soxr.cmake
│   ├── External_SDL2.cmake
│   ├── External_Libjxl.cmake
│   ├── External_NvcodecHeaders.cmake
│   ├── External_Openexr.cmake
│   ├── External_Highway.cmake
│   ├── External_Brotli.cmake
│   ├── External_Lcms2.cmake
│   └── External_FFmpeg.cmake
├── families/
│   ├── 7.x.cmake                      # FFmpeg 7.x (>=7.0 <8.0)
│   ├── 6.x.cmake                      # FFmpeg 6.x (>=6.0 <7.0)
│   ├── 4.x.cmake                      # FFmpeg 4.x (>=4.0 <5.0)
│   └── master.cmake                   # FFmpeg master (git)
└── patches/
    ├── zlib/msvc-shared-libs.patch
    ├── fribidi/msvc-gen-tab-disable.patch
    ├── ffmpeg/textutils-time-internal.patch
    ├── harfbuzz/msvc-pkgconfig-no-lm.patch
    ├── libjxl/msvc-pkgconfig-no-lm.patch
    ├── libvpx/msvc-build-fixes.patch
    └── x265/
        ├── msvc-static-pkgconfig.patch
        ├── msvc-shared-pkgconfig.patch
        ├── arm-emms-fix.patch
        └── cmake-policy.patch
```

## 使用方式

```bash
# 列出可用 preset
cmake --list-presets

# 构建方案 1: 共享 GPL 全量依赖
cmake --preset shared-gpl
cmake --build build/shared-gpl

# 构建方案 2: 静态最小化 (LGPL)
cmake --preset static-minimal
cmake --build build/static-minimal

# 同方案构建不同版本
cmake --preset shared-gpl -DFFMPEG_VERSION=7.2
cmake --preset shared-gpl -DFFMPEG_VERSION=master

# 禁用特定依赖
cmake --preset shared-gpl -DENABLE_DEP_X264=OFF

# 覆盖依赖版本
cmake --preset shared-gpl -DDEP_VERSION_OVERRIDE="zlib=1.2.13;x264=master"

# 生成发行说明
cmake --build build/shared-gpl --target release_note
```

构建输出位于 `build/<preset>/stage/`，包含 `bin/` `lib/` `include/` `lib/pkgconfig/`。

## 关键变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `FFMPEG_VERSION` | FFmpeg 版本 | `"7.1"` |
| `LINK_TYPE` | 链接方式 | `"shared"` |
| `LICENSE` | 许可证模式 | `"gpl"` |
| `CMAKE_MSVC_RUNTIME_LIBRARY` | CRT 链接 | `"MultiThreaded"` |
| `MSVC_CRT_FLAG` | CRT 编译标志（自动派生） | `"/MT"` |
| `TARGET_ARCH` | 目标架构 | `"amd64"` |
| `ENABLE_DEP_<NAME>` | 启用/禁用依赖 | `ON` |
| `DEP_VERSION_OVERRIDE` | 版本覆盖 (name=ver) | `""` |

## 架构限制

| 依赖 | x86 | amd64 | arm | arm64 |
|------|:--:|:-----:|:---:|:----:|
| x264 | ✅ | ✅ | ⚠️ `--disable-asm` | ⚠️ `--disable-asm` |
| FFmpeg | ✅ | ✅ | ⚠️ cross+no-asm | ⚠️ cross+no-asm |
| libass | ✅* | ✅* | ✅* | ✅* |
| libvpx | ✅ | ✅ | ⚠️ no-NEON | ⚠️ no-NEON |
| x265 | ✅ | ✅ | ⚠️ patch | ✅ |

\* libass 所有架构均 `--disable-asm`（MSVC 不兼容）

## 依赖项

- Visual Studio 2022（MSVC）
- MSYS2（含 make, diffutils, pkgconf, patch, yasm, nasm, meson, ninja）
- CMake 3.21+
- Git
