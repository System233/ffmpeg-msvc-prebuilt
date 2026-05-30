# AGENTS.md — AI 开发指南

本文档用于向新 AI 窗口交接项目上下文，使 AI 能快速理解项目结构、编码规范、当前问题优先级和扩展方式。

## 项目定位

CMake ExternalProject_Add 构建 FFmpeg + 16 个依赖的演示项目。通过 `ToolchainMSVC.cmake` 统一管理 CMake 编译工具项和环境变量，同时支撑 CMake 类和 autotools 类外部依赖。

⚠️ 当前为 Demo 阶段，仅集成 5/16 个依赖，存在 Windows shell 兼容性问题。

## 目录结构

```
ffmpeg-cmake-build/
├── CMakeLists.txt                # 主入口
│    ├─ 预处理（BUILD_TYPE/STAGE_DIR/Toolchain 等 CACHE 变量，project() 之前）
│    ├─ project() → 加载 ToolchainMSVC.cmake
│    └─ include(External_*.cmake)
│
├── cmake/
│   ├── ToolchainMSVC.cmake        # 统一工具链（CMake 工具 + 环境变量）
│   ├── BootstrapMSYS2.cmake       # MSYS2 检测（只读）
│   ├── External_Zlib.cmake         # CMake dep
│   ├── External_X264.cmake         # autotools dep
│   ├── External_Fribidi.cmake      # autogen + configure
│   ├── External_Libass.cmake       # depends fribidi
│   └── External_FFmpeg.cmake       # depends all
│
├── patches/
│   ├── zlib/msvc-shared-libs.patch
│   ├── fribidi/msvc-gen-tab-disable.patch
│   └── ffmpeg/textutils-time-internal.patch
│
├── README.md
├── AGENTS.md
└── .gitignore
```

## 代码规范

1. **External_*.cmake**: 一个文件一个依赖，按顺序：URL → PATCH → CONFIGURE → BUILD → INSTALL → BUILD_BYPRODUCTS
2. **变量引用**: 使用 `${VAR}` 风格，路径字符串加 `"${VAR}"` 引号
3. **PATCH_COMMAND**: 使用 `patch -p1 < <path>`，不用 git
4. **MSYS2 包裹**: autotools 命令用 `"${MSYS2_SHELL}" -lc "cd <DIR> && ..."` — 当前 demo 未修复
5. **ENVIRONMENT**: 不设置，自动从 ToolchainMSVC.cmake 继承 `ENV{CC}=cl` 等
6. **DEPENDS**: 多个依赖合并到一行 `DEPENDS a b c`
7. **BUILD_BYPRODUCTS**: MSVC 产物用 `.lib`/`.dll`（不是 `.dll.a`）
8. **URL_HASH**: 留空（demo 阶段不做 SHA256 校验）

## 核心机制：ToolchainMSVC.cmake

```cmake
# 原理：project() 在 CMake 加载时解析此文件。
# 同时设置 CMake 编译工具（给 CMake dep）和 ENV 变量（给 autotools dep）。
#
# CMake dep：通过 CMAKE_ARGS -DCMAKE_TOOLCHAIN_FILE=... 传递给子 cmake
# autotools dep：通过继承父进程环境变量获得 ENV{CC}=cl 等
#
# 注意：如果某 ExternalProject 显式设置了 ENVIRONMENT，继承机制完全失效，
# 所有 ENV{...} 需在该 ENVIRONMENT 中重复声明。

set(CMAKE_C_COMPILER    cl)    # CMake dep 继承
set(ENV{CC}             cl)    # autotools dep 继承
```

## ExternalProject_Add 模板

### CMake 项目

```cmake
ExternalProject_Add(<name>_target
    URL            <下载 URL>
    PATCH_COMMAND  cd <SOURCE_DIR> && patch -p1 < <patch_path>

    CMAKE_ARGS
        -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
        -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_RUNTIME}
        -DBUILD_SHARED_LIBS=${SHARED_LIBS}
        # dep 特有参数放在最后
)
```

注意：工具链文件必须是 CMAKE_ARGS 的第一个参数。

### Autotools 项目（需 MSYS2）

```cmake
ExternalProject_Add(<name>_target
    URL            <下载 URL>
    PATCH_COMMAND  cd <SOURCE_DIR> && patch -p1 < <patch_path>

    CONFIGURE_COMMAND
        "${MSYS2_SHELL}" -lc "cd <SOURCE_DIR> && ./configure --prefix=${STAGE_DIR} ..."

    BUILD_COMMAND
        "${MSYS2_SHELL}" -lc "cd <SOURCE_DIR> && ${CMAKE_MAKE_PROGRAM}"

    INSTALL_COMMAND
        "${MSYS2_SHELL}" -lc "cd <SOURCE_DIR> && ${CMAKE_MAKE_PROGRAM} install"

    BUILD_IN_SOURCE 1
)
```

### 依赖其他 dep

```cmake
ExternalProject_Add(<name>_target
    DEPENDS <prereq>_target
    ...
)
```

## 添加新依赖的完整步骤

1. 参考资料 `External_Zlib.cmake`（CMake）或 `External_X264.cmake`（autotools）创建 `cmake/External_<name>.cmake`
2. 如需补丁，放入 `patches/<name>/` 目录，在 `PATCH_COMMAND` 中用 `patch -p1`
3. 在 `CMakeLists.txt` 的 `# ---- Dependency Modules ----` 区域添加 `include("...")`
4. 如果被 FFmpeg 依赖，在 `External_FFmpeg.cmake` 的 `DEPENDS` 中添加
5. 验证：`cmake -S . -B build -G "Unix Makefiles"` 配置无错误
6. 验证：`cmake --build build --target <name>_target` 编译通过

## 当前已知问题的修复优先级

### P0 (阻断)

- [ ] **MSYS2 bash 包裹** — 所有 autotools dep 的 CONFIGURE/BUILD/INSTALL_COMMAND 须用 `${MSYS2_SHELL} -lc "..."` 包裹
- [ ] **补丁改为 patch -p1** — 移除 `git init && git apply`，改为 `patch -p1`
- [ ] **BUILD_TYPE 响应** — x264/FFmpeg 等 dep 根据 BUILD_TYPE 选择 shared/static 参数

### P1 (高优先级)

- [ ] **TARGET_ARCH 完整映射** — 添加 x86/arm/arm64 的 HOST_TRIPLE 和 ARCH_NAME 映射
- [ ] **LICENSE 筛选** — 添加 LICENSE cache 变量，GPL 时包含 x264/x265，LGPL 时排除
- [ ] **FFmpeg 版本选择** — `FFMPEG_VERSION` cache 变量，URL 模板化
- [ ] **剩余依赖集成** — 依次集成 freetype（CMake）、harfbuzz（CMake, depends freetype）、nv-codec-headers（make）、libvpx（autotools）、libwebp（CMake）、x265（CMake）、dav1d（CMake）、opus（CMake）、SDL2（CMake）、libjxl + openexr（CMake）、soxr（CMake）

### P2 (中优先级)

- [ ] **依赖参数集中管理** — 将 URL、版本、flags 统一到 CMake 变量列表或 JSON 清单，循环生成 External_*.cmake
- [ ] **CMakePresets.json** — 预置 amd64-shared-gpl / amd64-static-lgpl 等组合
- [ ] **GitHub Actions CI** — 构建 workflow
- [ ] **FATE 测试** — 构建后运行 FFmpeg 测试套件
- [ ] **Prebuilt SDK** — 自动打包 include/lib/bin/cmake，支持 `find_package(FFMPEG)`

### P3 (低优先级)

- [ ] **ccache/sccache** — 加速 MSVC 构建
- [ ] **Ninja 备选** — 支持 `-G Ninja` 生成器

## 验证命令

```bash
# 配置 — 检查有否 fatal error
cmake -S . -B build -G "Unix Makefiles"

# 构建单个 dep（输出可控，建议用此逐步验证）
cmake --build build --target zlib_target

# 全量构建
cmake --build build --parallel 4
```

## 文件依赖关系

```
CMakeLists.txt
  ├── BootstrapMSYS2.cmake       (MSYS2_SHELL / MSYS2_ROOT)
  ├── ToolchainMSVC.cmake         (C_COMPILER / ENV vars)
  │     └── BootstrapMSYS2.cmake  (间接依赖: ENV{MSYSTEM}/ENV{MSYS2_PATH_TYPE} 确保 make 行为正确)
  ├── External_Zlib.cmake         (参考模板)
  ├── External_X264.cmake         (参考模板)
  ├── External_Fribidi.cmake      (参考模板)
  ├── External_Libass.cmake       (depends fribidi)
  └── External_FFmpeg.cmake       (depends all)
```

## 参考资源

| 资源 | 位置 | 用途 |
|------|------|------|
| Python 构建器 | `../ffmpeg_builder/` | 参考旧的构建逻辑（dep 版本/URL/补丁/特殊参数含义） |
| 版本清单 | `../manifests/` | 将来整合的依赖版本配置 |
| 原始补丁 | `../patches/` | 补丁来源（与 Python 构建器共享） |
| build.py | `../build.py` | MSVC+MSYS2 环境启动器 |
| cmake 帮助 | `cmake --help-command ExternalProject_Add` | 完整参数文档 |

## CMake 关键变量

| 变量 | 来源 | 用途 |
|------|------|------|
| STAGE_DIR | CMakeLists.txt CACHE | 所有 dep 安装前缀 |
| CFLAGS_MODE | 由 BUILD_TYPE 推导 | `/MT`(static) 或 `/MD`(shared) |
| SHARED_LIBS | 由 BUILD_TYPE 推导 | `OFF`(static) 或 `ON`(shared) |
| MSVC_RUNTIME | 由 BUILD_TYPE 推导 | `MultiThreaded`(static) 或 `MultiThreadedDLL`(shared) |
| MSYS2_SHELL | BootstrapMSYS2.cmake | MSYS2 bash.exe 路径 |
| CMAKE_TOOLCHAIN_FILE | CMakeLists.txt CACHE | ToolchainMSVC.cmake 路径 |
| CMAKE_MAKE_PROGRAM | CMake 自动 | 当前生成器的 make 程序 |
