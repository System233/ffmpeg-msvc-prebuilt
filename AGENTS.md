# AGENTS.md — AI 开发指南

## 项目定位

CMake ExternalProject_Add 构建 FFmpeg + 16 个依赖。通过 `DepPackage.cmake` 宏系统实现 NPM 风格的依赖注册、版本管理、传递依赖解析。通过 `CMakePresets.json` + `families/*.cmake` 实现版本族方案复用。

## 目录结构

```
ffmpeg-cmake-build/
├── CMakeLists.txt                    # 5-Phase 主入口
├── CMakePresets.json                 # 构建方案预设
├── cmake/
│   ├── ToolchainMSVC.cmake           # 统一工具链 (CMake 工具 + ENV 变量)
│   ├── BootstrapMSYS2.cmake          # MSYS2 检测
│   ├── DepPackage.cmake              # 宏: dep_package, dep_package_version, ffmpeg_family
│   ├── DepResolver.cmake             # 宏: dep_resolve_all (版本匹配 + 依赖解析)
│   ├── BuildAssembly.cmake           # 遍历 RESOLVED_DEPS 调用 build_*()
│   ├── ReleaseNote.cmake             # add_custom_target(release_note)
│   ├── compile                       # GNU Automake 包装器 (libvpx MSVC fix)
│   ├── External_Zlib.cmake           # CMake dep
│   ├── External_X264.cmake           # autotools dep
│   ├── External_X265.cmake           # CMake dep (GPL)
│   ├── External_Fribidi.cmake        # autotools dep
│   ├── External_Freetype.cmake       # CMake dep
│   ├── External_Harfbuzz.cmake       # CMake dep (REQUIRES freetype)
│   ├── External_Libass.cmake         # autotools dep (REQUIRES fribidi;freetype)
│   ├── External_Libvpx.cmake         # autotools dep (arch-specific target)
│   ├── External_Libwebp.cmake        # CMake dep
│   ├── External_Dav1d.cmake          # meson dep
│   ├── External_Opus.cmake           # CMake dep
│   ├── External_Soxr.cmake           # CMake dep
│   ├── External_SDL2.cmake           # CMake dep
│   ├── External_Libjxl.cmake         # CMake dep (REQUIRES highway;brotli;lcms2)
│   ├── External_NvcodecHeaders.cmake # autotools dep (头文件仅)
│   ├── External_Openexr.cmake        # CMake dep (已禁用)
│   ├── External_Highway.cmake        # CMake dep
│   ├── External_Brotli.cmake         # CMake dep
│   ├── External_Lcms2.cmake          # CMake dep
│   └── External_FFmpeg.cmake         # autotools dep (depends all)
├── families/
│   ├── 7.x.cmake                      # FFmpeg 7.x 族
│   ├── 6.x.cmake                      # FFmpeg 6.x 族
│   ├── 4.x.cmake                      # FFmpeg 4.x 族
│   └── master.cmake                   # FFmpeg master 族
└── patches/
    ├── zlib/msvc-shared-libs.patch
    ├── fribidi/msvc-gen-tab-disable.patch
    ├── ffmpeg/textutils-time-internal.patch
    ├── harfbuzz/msvc-pkgconfig-no-lm.patch
    ├── libjxl/msvc-pkgconfig-no-lm.patch
    ├── libvpx/msvc-build-fixes.patch
    └── x265/(4 patches)
```

## 代码规范

1. **External_*.cmake**: 注册部分在上（dep_package + dep_package_version），构建函数在下（build_<name>()）
2. **PATCH_COMMAND**: 统一使用 `PATCH_COMMAND ${NAME}_RESOLVED_PATCH_CMDS}`（由 DepResolver 生成，无补丁时为空）
3. **PATCHES 路径**: 从 `patches/` 开始的全路径，含 `.patch` 扩展名。例如 `zlib/msvc-shared-libs.patch`
4. **DEPENDS**: 使用 `${NAME}_RESOLVED_DEPENDS}`（由 DepResolver 从 REQUIRES 自动生成）
5. **BUILD_BYPRODUCTS**: MSVC 产物用 `.lib`/`.dll`
6. **CRT**: `CMAKE_MSVC_RUNTIME_LIBRARY` 为唯一真源，CMake deps 通过 CMAKE_ARGS 传递，autotools deps 通过 `MSVC_CRT_FLAG`（自动派生）
7. **CMake deps**: 必须包含 `-DCMAKE_POLICY_DEFAULT_CMP0091=NEW`
8. **$(MAKE)**: autotools deps 必须使用 `$(MAKE)`（不是 `${CMAKE_MAKE_PROGRAM}`）
9. **SOURCE_SUBDIR**: 源码 CMakeLists.txt 在子目录时使用（如 x265 `source/`）

## 核心机制

### ToolchainMSVC.cmake

```
project() 加载 → CMake 变量 (CMake dep) + ENV 变量 (autotools dep)
  ├─ CMAKE_C_COMPILER=cl          →  CMake dep 通过 CMAKE_TOOLCHAIN_FILE 继承
  ├─ ENV{CC}=cl                  →  autotools dep 通过子进程继承
  ├─ CMAKE_C_FLAGS += MSVC_CRT_FLAG  →  autotools dep 通过 SHELL_ENV 前缀
  └─ STAGE_DIR_UNIX              →  PKG_CONFIG_PATH 使用 Unix 路径
```

### DepPackage.cmake 宏系统

```
dep_package(NAME zlib DEFAULT 1.3.1 BUILD cmake FFMPEG_FLAG --enable-zlib)
dep_package_version(NAME zlib VERSION 1.3.1 URL "..." PATCHES zlib/msvc-shared-libs.patch)

ffmpeg_family(NAME 7.x VERSION_RANGE ">=7.0 <8.0" DEPS zlib>=1.2.0 x264 fribidi>=1.0.0 ...)
```

### DepResolver.cmake

```
dep_resolve_all():
  1. 匹配 FFMPEG_VERSION → family
  2. 解析 FFmpeg URL/补丁/flags
  3. 解析 family DEPS (name>=ver 语法)
  4. 创建 ENABLE_DEP_* CACHE BOOL (默认 ON)
  5. License 检查 (lgpl → 排除 GPL dep)
  6. DFS 递归解析 (transitive REQUIRES)
  7. 生成 RESOLVED_DEPS, FFMPEG_ASM_DEPENDS, FFMPEG_ASM_FLAGS, ${NAME}_RESOLVED_*
```

### BuildAssembly.cmake

```
foreach dep IN RESOLVED_DEPS:
    cmake_language(CALL build_${dep})
build_ffmpeg()
```

注意：必须使用 `cmake_language(CALL build_${dep})` 而非 `build_${dep}()`，后者在 foreach 中展开异常。

## 构建系统类型模板

### CMake dep

```cmake
dep_package(NAME <name> DEFAULT <ver> BUILD cmake FFMPEG_FLAG --enable-<name> REQUIRES <prereq> LICENSE <license>)
dep_package_version(NAME <name> VERSION <ver> URL "<url>" PATCHES <patch1>;<patch2>)

function(build_<name>)
    ExternalProject_Add(<name>_target
        DEPENDS      ${<UPPER>_RESOLVED_DEPENDS}
        URL          ${<UPPER>_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/<name>"
        PATCH_COMMAND ${<UPPER>_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_PREFIX_PATH=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
            # dep 特有参数
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/<name>.lib"
            "${STAGE_DIR}/lib/pkgconfig/<name>.pc"
    )
endfunction()
```

### autotools dep

```cmake
dep_package(NAME <name> DEFAULT <ver> BUILD autotools FFMPEG_FLAG --enable-<name>)
dep_package_version(NAME <name> VERSION <ver> URL "<url>" PATCHES <patch>)

function(build_<name>)
    ExternalProject_Add(<name>_target
        URL          ${<UPPER>_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/<name>"
        PATCH_COMMAND ${<UPPER>_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ${SHELL_ENV} ./configure
                --prefix=${STAGE_DIR}
                ...
        BUILD_COMMAND   $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS ...
    )
endfunction()
```

### meson dep

```cmake
dep_package(NAME <name> DEFAULT <ver> BUILD meson FFMPEG_FLAG --enable-<name>)

function(build_<name>)
    ExternalProject_Add(<name>_target
        URL          ${<UPPER>_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/<name>"
        CONFIGURE_COMMAND
            ${SHELL_ENV} meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --buildtype=release
                --default-library=static
                --vsenv
        BUILD_COMMAND   meson compile -C <BINARY_DIR>
        INSTALL_COMMAND meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS ...
    )
endfunction()
```

## 添加新依赖

1. 创建 `cmake/External_<Name>.cmake`：
   - 注册：`dep_package(NAME <lower> DEFAULT <ver> BUILD <type> ...)`
   - 版本：`dep_package_version(NAME <lower> VERSION <ver> URL "..." PATCHES ...)`
   - 构建：`function(build_<lower>) ... endfunction()`
2. 如有补丁，放入 `patches/<name>/`，PATCHES 使用完整路径（含扩展名）
3. 在 `CMakeLists.txt` Phase 1 中添加 `include(".../External_<Name>.cmake")`
4. 如需纳入 family 默认依赖，在 `families/*.cmake` 的 `DEPS` 中添加
5. 如有传递依赖（REQUIRES），DepResolver 自动处理，无需手动配置 DEPENDS
6. 验证：重新配置并构建单个 dep 目标

## 版本族

```
families/7.x.cmake:
  ffmpeg_family(NAME 7.x VERSION_RANGE ">=7.0 <8.0" DEPS zlib>=1.2.0 x264 fribidi>=1.0.0 ...)
  → DEPS 语法: "name" (默认启用) 或 "name>=ver" (启用+版本约束)

families/master.cmake:
  ffmpeg_family(NAME master VERSION_MATCH "^master$" URL "..." URL_TYPE git DEPS ...)
  → VERSION_MATCH 用于正则匹配（替代 VERSION_RANGE）
```

## 用户接口

| 变量 | 用途 | 示例 |
|------|------|------|
| `FFMPEG_VERSION` | FFmpeg 版本 | `-DFFMPEG_VERSION=7.2` |
| `LINK_TYPE` | 链接方式 | `-DLINK_TYPE=static` |
| `LICENSE` | 许可证 | `-DLICENSE=lgpl` |
| `ENABLE_DEP_<NAME>` | 启用/禁用 | `-DENABLE_DEP_X264=OFF` |
| `DEP_VERSION_OVERRIDE` | 版本覆盖 | `-DDEP_VERSION_OVERRIDE="zlib=1.2.13"` |
| `TARGET_ARCH` | 架构 | `-DTARGET_ARCH=arm64` |

## 关键变量

| 变量 | 来源 | 用途 |
|------|------|------|
| `STAGE_DIR` | CMakeLists.txt CACHE | 所有 dep 安装前缀 (Windows 路径) |
| `STAGE_DIR_UNIX` | ToolchainMSVC.cmake | PKG_CONFIG_PATH 用 Unix 路径 |
| `CMAKE_MSVC_RUNTIME_LIBRARY` | CMakeLists.txt CACHE | CRT 链接方式 (MultiThreaded/MultiThreadedDLL) |
| `MSVC_CRT_FLAG` | CMakeLists.txt 派生 | autotools dep 用 CRT 标志 (/MT /MD /MTd /MDd) |
| `LINK_TYPE` | CMakeLists.txt CACHE | FFmpeg shared/static 选择 |
| `SHELL_ENV` | ToolchainMSVC.cmake | autotools dep 环境前缀 (CC=cl CXX=cl ...) |
| `TARGET_ARCH` | CMakeLists.txt CACHE | 目标架构映射 (ARCH_NAME/HOST_TRIPLE) |
| `RESOLVED_DEPS` | DepResolver.cmake | 解析后的构建顺序列表 |
| `${NAME}_RESOLVED_DEPENDS` | DepResolver.cmake | 单个 dep 的 ExternalProject DEPENDS |
| `${NAME}_RESOLVED_PATCH_CMDS` | DepResolver.cmake | 单个 dep 的 PATCH_COMMAND 列表 |
| `${NAME}_RESOLVED_URL` | DepResolver.cmake | 解析后的下载 URL |
