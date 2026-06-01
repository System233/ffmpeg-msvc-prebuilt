# FFmpeg MSVC Build — 问题知识库

## 构建环境

### 前置工具
- CMake, Meson, Ninja
- MSYS2 (位于 `d:\msys64\`)
- Visual Studio 2022 (含 MSVC 工具链)

### 启动流程
```
1. 打开 "Developer Command Prompt for VS 2022"
2. set MSYS2_PATH_TYPE=inherit        # 继承 PATH 环境变量
3. set MSYS2_ARG_CONV_EXCL=*          # 阻止 MSYS2 自动路径转换
4. set PKG_CONFIG_LIBDIR="" PKG_CONFIG_PATH="" # 清除默认搜索路径
5. d:\msys64\ucrt64.exe               # 启动 UCRT64 环境 (pkgconf 支持 Windows 路径)
6. 在 UCRT64 shell 中执行 cmake --build ...
```

### 路径约束
- 构建路径（工作目录）中不得包含空格，否则 autotools/MSYS2 路径解析失败。
- `STAGE_DIR_UNIX` 由 ToolchainMSVC.cmake 通过 `cygpath -u` 转换，供 MSYS2 pkgconf 使用。

## 自测流程

```
1. cmake --build build --target ffmpeg_target 2>&1
2. 若失败 → 读取 build/src/ffmpeg/ffbuild/config.log 尾部 200 行（文件极长，勿读全文）
3. 检查 build/stage/lib/ 和 build/stage/lib/pkgconfig/ 文件列表（ls -la）
4. 缺失/名称错误 → 修复对应 cmake/External_*.cmake → 回到第1步
5. 重复直到 FFmpeg configure 通过（config.log 末尾显示成功或新错误）
```

**重要**: 只运行 `cmake --build`，不要手动 reconfigure。CMake 检测 cmake/*.cmake 变更后自动 reconfigure。

## stage 目录结构

```
build/stage/
├── include/   # 头文件
├── lib/       # .lib 文件
│   └── pkgconfig/  # .pc 文件
└── share/
```

## PkgConfigHelper 宏（cmake/PkgConfigHelper.cmake）

三个宏定义，在 CMakeLists.txt Phase 1 已 include：

### 1. add_pkgconfig_file(target pc_file lib_name version description [REQUIRES dep1;dep2])
生成 .pc 文件并挂载安装后复制步骤。
**必须放在 ExternalProject_Add 之后**（内部调用 ExternalProject_Add_Step，target 必须先存在）。
```cmake
add_pkgconfig_file(aom_target aom.pc aom 3.11.0 "AV1 codec library")
add_pkgconfig_file(foo_target foo.pc foo 1.0 "Foo library" REQUIRES bar;baz)
```

### 2. add_rename_step(target from to)
将 libxxx.a 复制为 xxx.lib（meson 产物兼容）。
```cmake
add_rename_step(dav1d_target libdav1d.a dav1d.lib)
add_rename_step(liblc3_target liblc3.a lc3.lib)
add_rename_step(vmaf_target libvmaf.a vmaf.lib)
```

### 3. patch_pkg_config(prefix)
批量重定位 .pc 文件中硬编码的 STAGE_DIR 路径为 `${pcfiledir}/../..`。
```cmake
patch_pkg_config(${STAGE_DIR})
```

## 常见问题及修复

### A. 库的 .pc 文件缺失
**症状**: config.log 末尾 `ERROR: xxx not found using pkg-config`
**修复**: 在 External_*.cmake 的 build 函数中，ExternalProject_Add(...) 之后调用:
```cmake
add_pkgconfig_file(target_name pc_file lib_name version "description")
```

### B. 库文件扩展名不匹配 (.a vs .lib)
**症状**: stage/lib/ 下有 libxxx.a 但无 xxx.lib
**修复**: ExternalProject_Add(...) 之后调用:
```cmake
add_rename_step(target_name libxxx.a xxx.lib)
```

### C. 库名不匹配
**症状**: FFmpeg 找不到库，stage/lib/ 检测发现实际输出文件名与 BUILD_BYPRODUCTS 不同
**修复**: 修改 BUILD_BYPRODUCTS 中的文件名。若差异为 .a↔.lib，用 add_rename_step。

### D. meson 项目需要多个编译选项
**三个要点**:

**要点1**: 多 flag 用 JSON 数组语法（非多个 -Dc_args）:
```cmake
CONFIGURE_COMMAND
    ${SHELL_ENV} meson setup <BINARY_DIR> <SOURCE_DIR>
        -Dc_args="${CMAKE_C_FLAGS}"
        "-Dc_args=[\"flag1\",\"flag2\",\"flag3\"]"
        ...
```

**要点2**: 必须加 `-Db_vscrt=mt` 对齐 CRT:
```cmake
        -Db_vscrt=mt
```

**要点3**: 单 flag 简写:
```cmake
        -Dc_args="${CMAKE_C_FLAGS}"
```

### E. 纯 Makefile 构建（无 configure 脚本）
**症状**: `./configure: No such file or directory`
**修复**: CONFIGURE_COMMAND 置空，BUILD_COMMAND 直接用 $(MAKE):
```cmake
CONFIGURE_COMMAND ""
BUILD_COMMAND
    $(MAKE) -C <SOURCE_DIR>
        CC=${CMAKE_CURRENT_LIST_DIR}/compile-cl
        AR=${CMAKE_CURRENT_LIST_DIR}/compile-lib
BUILD_IN_SOURCE 1
```

### F. MSVC 不支持 C99 VLA
**症状**: `error C2057: expected constant expression`, `error C2466: cannot allocate an array of constant size 0`
**修复**: 该库不兼容 MSVC。在 families/*.cmake 中注释该 dep 行，在 CMakeLists.txt 中注释对应 include 行。

### G. GCC 专用编译选项
**症状**: `cl : Command line warning D9002 : ignoring unknown option`
**修复**: 创建补丁用 `if(NOT MSVC)` 包裹 GCC 专用选项（-Wall, -std=gnu11 等）。

### H. autotools 硬依赖
**症状**: `configure: error: Please install xxx`
**修复**: 在 dep_package 中添加 `REQUIRES xxx`，注册对应 External_*.cmake。

### I. URL 404 / tag 格式
**症状**: download 步骤 HTTP error
**修复**: 确认 GitHub 标签实际名称（tag 可能无 `v` 前缀）。

### J. 缺失 pthread.h
**症状**: `fatal error C1083: Cannot open include file: 'pthread.h'`
**修复**: 添加 `REQUIRES pthreads`，库名 `pthreadVSE3.lib`（GerHobbelt/pthread-win32）。

### K. 原子操作未启用
**症状**: `fatal error C1189: #error: "C atomic support is not enabled"`
**修复**: 在 meson c_args 中添加 `-Dc_args="[\"/experimental:c11atomics\"]"`。

## 项目配置摘要

- 构建: MSVC (cl.exe), CMake ExternalProject_Add
- 工具链: cmake/ToolchainMSVC.cmake
- autotools: ${SHELL_ENV} ./configure --host=${HOST_TRIPLE} ..., $(MAKE) -C <SOURCE_DIR>
- meson: ${SHELL_ENV} meson setup --vsenv -Db_vscrt=mt --default-library=static
- CMake: CMAKE_POLICY_DEFAULT_CMP0091=NEW, CMAKE_MSVC_RUNTIME_LIBRARY
- 宏: cmake/PkgConfigHelper.cmake
- 解析: cmake/DepResolver.cmake (REQUIRES 自动生成 RESOLVED_DEPENDS)
- 已禁用: codec2, speex (VLA); vmaf (7.x, MSVC 实验性)
