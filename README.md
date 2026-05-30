# FFmpeg CMake ExternalProject Build Demo

使用 CMake ExternalProject_Add 构建 FFmpeg 及其依赖的**演示项目**。支持 MSVC 编译器、"Unix Makefiles" 生成器，通过 `cmake/ToolchainMSVC.cmake` 统一管理编译工具链和环境变量。

⚠️ **Demo 状态** — 当前为概念验证阶段，仅集成 5/16 个依赖，存在 Windows shell 兼容性问题。详见下文「已知问题」。

## 当前依赖 (5/16)

| 依赖 | 构建系统 | 状态 | 许可证 |
|------|---------|------|--------|
| zlib 1.3.1 | CMake | ✅ 已集成 | zlib |
| x264 master | autotools | ⚠️ 需 MSYS2 包裹 | GPL |
| fribidi 1.0.16 | autogen+configure | ⚠️ 需 MSYS2 包裹 | LGPL |
| libass 0.17.3 | autotools | ⚠️ 需 MSYS2 包裹 | ISC |
| FFmpeg 7.1 | autotools | ⚠️ 需 MSYS2 包裹 | GPL/LGPL |

## 待集成依赖清单

P0（构建系统核心）:
- nv-codec-headers — make（仅头文件分发）
- freetype 2.13.3 — CMake
- harfbuzz 10.1.0 — CMake（depends freetype）

P1（常用编解码）:
- libvpx 1.15.0 — autotools（需 yasm）
- libwebp 1.5.0 — CMake
- x265 4.1 — CMake（GPL）
- dav1d 1.5.1 — CMake
- opus 1.5.2 — CMake
- SDL 2.30.11 — CMake（ffplay 需要）

P2（高级/扩展）:
- libjxl 0.11.1 — CMake（depends openexr）
- openexr 3.3.2 — CMake（libjxl 的子依赖）
- soxr 0.1.3 — CMake

## 架构

```
CMakeLists.txt
│
├─ 预处理 (project() 之前)
│    BUILD_TYPE: static / shared
│      → CFLAGS_MODE: /MT 或 /MD
│      → SHARED_LIBS: OFF 或 ON
│      → MSVC_RUNTIME: MultiThreaded(Static) 或 MultiThreadedDLL
│    STAGE_DIR: 统一安装前缀
│    CMAKE_TOOLCHAIN_FILE = cmake/ToolchainMSVC.cmake
│
├─ project() → 加载 ToolchainMSVC.cmake
│    │
│    ├─ CMake 编译工具 (CMake dep 通过 CMAKE_TOOLCHAIN_FILE 继承)
│    │    CMAKE_C_COMPILER=cl
│    │    CMAKE_RC_COMPILER=rc     (修复 windres 问题)
│    │    CMAKE_AR=lib
│    │    CMAKE_LINKER=link
│    │    CMAKE_MT=mt
│    │
│    └─ 环境变量 (autotools dep 继承父进程)
│         ENV{CC}=cl
│         ENV{CXX}=cl
│         ENV{CFLAGS}=/MD
│         ENV{PKG_CONFIG_PATH}=$STAGE_DIR/lib/pkgconfig:$STAGE_DIR/share/pkgconfig
│         ENV{MSYSTEM}=MSYS
│         ENV{MSYS2_PATH_TYPE}=inherit
│
├─ include(External_*.cmake)
│    各 dep 参数在独立文件中定义
│
└─ add_custom_target(all_deps DEPENDS ffmpeg_target)
```

## 项目结构

```
ffmpeg-cmake-build/
├── CMakeLists.txt                    # 主入口
├── .gitignore
├── README.md
├── AGENTS.md
├── cmake/
│   ├── ToolchainMSVC.cmake           # 统一工具链
│   ├── BootstrapMSYS2.cmake          # MSYS2 路径检测
│   ├── External_Zlib.cmake           # CMake dep
│   ├── External_X264.cmake           # autotools dep
│   ├── External_Fribidi.cmake        # autogen + configure
│   ├── External_Libass.cmake         # depends fribidi
│   └── External_FFmpeg.cmake         # depends all
└── patches/
    ├── zlib/msvc-shared-libs.patch
    ├── fribidi/msvc-gen-tab-disable.patch
    └── ffmpeg/textutils-time-internal.patch
```

## 使用方式

```bash
# 建议从项目根目录执行 build.py 以获取 MSVC+MSYS2 环境

# 配置
python ../build.py -a x64 -- cmake -S . -B build -G "Unix Makefiles"

# 全量构建
python ../build.py -a x64 -- cmake --build build --parallel 4

# 构建单个目标
python ../build.py -a x64 -- cmake --build build --target zlib_target

# 只构建 FFmpeg（依赖已就绪时）
python ../build.py -a x64 -- cmake --build build --target ffmpeg_target

# 仅配置但不构建
cmake -S . -B build -G "Unix Makefiles"

# 清理
cmake --build build --target clean
```

构建输出位于 `build/stage/`，包含 `bin/` `lib/` `include/` `lib/pkgconfig/`。

## 已知问题

### 1. Windows Shell 兼容性 (P0 阻断)

所有 autotools dep 的 `CONFIGURE_COMMAND` / `BUILD_COMMAND` 使用 Unix shell 语法（`cd`、`./configure`、`export`），但 ExternalProject 在 Windows 上通过 `cmd /c` 执行，不是 MSYS2 bash。

当前 `BootstrapMSYS2.cmake` 已检测 MSYS2 路径 (`MSYS2_SHELL`)，但未被任何 ExternalProject 引用。

**修复方案**：所有 autotools command 用 `${MSYS2_SHELL} -lc "..."` 包裹。

```cmake
# 修复前（cmd.exe 无法运行）
CONFIGURE_COMMAND
    cd <SOURCE_DIR> && ./configure --prefix=${STAGE_DIR}

# 修复后
CONFIGURE_COMMAND
    "${MSYS2_SHELL}" -lc
    "cd <SOURCE_DIR> && ./configure --prefix=${STAGE_DIR}"
```

### 2. 构建参数硬编码 (P1)

| 参数 | 当前状态 | 目标 |
|------|---------|------|
| BUILD_TYPE (static/shared) | CFLAGS_MODE/SHARED_LIBS/MSVC_RUNTIME 正确推导，但 x264/FFmpeg 未使用 | 每个 dep 根据 BUILD_TYPE 选择 `--enable-shared` 或 `--enable-static` |
| TARGET_ARCH (x86/amd64/arm/arm64) | HOST_TRIPLE 和 ARCH_NAME 仅完整映射 amd64 | 需完整映射 4 种架构，配置给 --host、--arch 等参数 |
| FFmpeg 版本 | 硬编码 `ffmpeg-7.1.tar.xz` | 需 cache 变量：`set(FFMPEG_VERSION "7.1" CACHE STRING "")` |
| GPL/LGPL | 硬编码 `--enable-gpl` | 需 LICENSE cache 变量筛选 x264/x265 |
| FFmpeg configure args | 硬编码 `--enable-zlib` 等 | 需从依赖列表动态生成 |

### 3. 补丁使用 git init (P1)

当前 `PATCH_COMMAND` 使用 `git init && git apply`。对于 tarball 下载的源码没有 `.git` 目录，`git init` 多余。应改用 `patch -p1`：

```cmake
PATCH_COMMAND
    "${MSYS2_SHELL}" -lc "cd <SOURCE_DIR> && patch -p1 < .../patches/zlib/msvc-shared-libs.patch"
```

### 4. 依赖参数分散 (P2)

每个 `External_*.cmake` 独立管理 URL、configure flags、patch 路径。不利于维护和版本切换。理想方案：从 manifests/JSON 或统一 CMake 变量列表生成。

### 5. 当前补丁体系与主项目共享

补丁文件在 `patches/` 下与主项目（`ffmpeg_builder/` Python 构建器）共享。修改补丁时需确保两套构建系统同步。

## 文件职责

| 文件 | 职责 | 可修改？ |
|------|------|:-------:|
| CMakeLists.txt | CACHE 变量定义 + include 所有 External_*.cmake | ✅ 添加新 dep 时 |
| ToolchainMSVC.cmake | 编译工具 + 环境变量 | ⚠️ 稳定后只读 |
| BootstrapMSYS2.cmake | MSYS2 路径检测 | ❌ 只读 |
| External_*.cmake | 单个 dep 的下载/补丁/配置/编译/安装 | ✅ 每个 dep 一个 |
| patches/*    | MSVC 兼容补丁 | ✅ 按需添加/修改 |

## 构建系统类型参考

### 类型 A: CMake 项目

模板：`cmake/External_Zlib.cmake`

```cmake
ExternalProject_Add(<name>_target
    URL       ...
    PATCH_COMMAND
        cd <SOURCE_DIR> && patch -p1 < <patch_path>

    CMAKE_ARGS
        -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
        -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_RUNTIME}
        -DBUILD_SHARED_LIBS=${SHARED_LIBS}
        # dep 特有参数
)
```

### 类型 B: autotools + configure

模板：`cmake/External_X264.cmake`

```cmake
ExternalProject_Add(<name>_target
    URL       ...
    CONFIGURE_COMMAND
        "${MSYS2_SHELL}" -lc "cd <SOURCE_DIR> && ./configure --prefix=${STAGE_DIR} ..."
    BUILD_COMMAND
        "${MSYS2_SHELL}" -lc "cd <SOURCE_DIR> && ${CMAKE_MAKE_PROGRAM}"
    INSTALL_COMMAND
        "${MSYS2_SHELL}" -lc "cd <SOURCE_DIR> && ${CMAKE_MAKE_PROGRAM} install"
    BUILD_IN_SOURCE 1
)
```

### 类型 C: autogen + configure

fribidi / libass 在 configure 前先需要 `NOCONFIGURE=1 ./autogen.sh`。

### 类型 D: 依赖其他 dep

libass → fribidi、harfbuzz → freetype、libjxl → openexr。

```cmake
ExternalProject_Add(<name>_target
    DEPENDS <prereq>_target
    ...
)
```

## 完整依赖 DAG

```
zlib ────────┐
freetype ──→ harfbuzz ───┐
fribidi ──→ libass ──────┤
openexr ──→ libjxl ──────┤
x264 ────────────────────┤
x265 ────────────────────┤
nv-codec-headers ────────┤
libvpx ──────────────────┤
libwebp ─────────────────┤
dav1d ───────────────────┤
opus ────────────────────┤
soxr ────────────────────┤
SDL2 ────────────────────┤
                          ├──→ ffmpeg
```

## 依赖项

- Visual Studio 2022（MSVC）
- MSYS2 到 D:/msys64（含 make, diffutils, pkgconf, patch, yasm, nasm）
- CMake 3.21+
- Git

测试未集成。
