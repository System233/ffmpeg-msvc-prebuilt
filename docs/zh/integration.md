# 开发集成

## 前置条件

下载与目标应用架构一致的 **共享库二进制**，按[使用指南](../guide/#下载完整性校验)校验后解压。例如 `C:\Tools\ffmpeg`，该目录应包含 `bin/`、`lib/`、`include/` 和 `share/ffmpeg/`。完整静态 SDK 体积过大，静态库构建仅分发命令行工具；静态链接开发请[自行构建](../self-build/)。

## 最小版本

使用 CMake 3.21+ 和 MSVC。在项目目录创建以下两个文件。

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

在 PowerShell 中配置、编译并运行（以下以 Visual Studio 多配置生成器、x64 为例）：

```powershell
cmake -S . -B build -A x64 "-DFFMPEG_ROOT=C:/Tools/ffmpeg"
cmake --build build --config Release
$env:Path = "C:\Tools\ffmpeg\bin;$env:Path"
.\build\Release\myapp.exe
```

程序应输出 FFmpeg 版本。ARM64、x86、ARM 需选择对应生成器平台（x86 使用 Win32）；Ninja 等生成器需要在相应 MSVC 工具链环境中配置，不传 `-A`。

## 带 DLL 自动部署（Windows 共享构建）

在上述 `CMakeLists.txt` 末尾追加以下代码，构建完成后自动复制匹配的 DLL，无需修改运行时 PATH。安装时也一并复制 DLL。

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

随应用分发前，请阅读[许可证与再分发](../licenses/)。

## 调试构建与符号

1. 下载同一构建批次、架构、许可证和链接方式的调试库，覆盖解压到 共享库二进制目录。旧版完整 Develop 包可直接使用。
2. 重新配置并执行 `cmake --build build --config Debug`；如采用自动部署，运行 Debug 输出目录中的程序。
3. 在 Visual Studio「调试 → 窗口 → 模块」检查实际加载的 DLL 与 PDB 是否匹配。

新版 CMake 模块在完整 Debug 库和 DLL 可用时选择 Debug 配置，否则使用 Release 库。Release PDB 位于 `bin/`（如果提供），Debug DLL/PDB 位于 `debug/bin/`。不要混用不同构建的库和符号。

## 其他链接方式

按需链接时，将 `target_link_libraries` 替换为：

```cmake
target_link_libraries(myapp PRIVATE
    FFmpeg::avformat FFmpeg::avcodec FFmpeg::avutil
)
```

旧项目也可使用 `${FFMPEG_INCLUDE_DIRS}` 和 `${FFMPEG_LIBRARIES}`；不使用 CMake 时，手动添加 `include/`、`lib/`，链接所需的导入库，并部署 `bin/` 中的匹配 DLL。变量方式不提供导入目标的自动 DLL 解析，需自行部署。

## 工作原理

`FFMPEG_ROOT` 指向 SDK 根目录；`CMAKE_MODULE_PATH` 使 CMake 找到随包提供的 `FindFFmpeg.cmake`。该模块查找头文件、导入库和 DLL，创建导入目标，并按配置选择库。`FFmpeg::FFmpeg` 聚合所有可用模块；`TARGET_RUNTIME_DLLS` 根据导入目标解析运行时 DLL。更换 SDK 后重新配置，旧版模块必要时使用新的构建目录。

## 可用目标

| 目标 | 用途 |
|---|---|
| `FFmpeg::FFmpeg` | 所有可用模块 |
| `FFmpeg::avutil` | 通用工具 |
| `FFmpeg::avcodec` | 编解码 |
| `FFmpeg::avformat` | 封装与解封装 |
| `FFmpeg::avfilter` | 滤镜 |
| `FFmpeg::avdevice` | 设备输入输出 |
| `FFmpeg::swresample` | 音频重采样 |
| `FFmpeg::swscale` | 图像缩放及色彩转换 |

兼容旧命名 `FFMPEG::ffmpeg` 和 `FFMPEG::avcodec` 等。模块是否可用取决于版本及构建配置。

## 可用变量

| 变量 | 说明 |
|---|---|
| `FFMPEG_FOUND` / `FFMPEG_VERSION` | 查找结果 / 版本 |
| `FFMPEG_INCLUDE_DIRS` | 头文件搜索路径 |
| `FFMPEG_LIBRARY_DIRS` | 库搜索路径 |
| `FFMPEG_LIBRARIES` / `FFMPEG_LIBRARY` | 库列表 |

模块级变量使用 `FFMPEG_lib<name>_` 前缀，例如 `FFMPEG_libavcodec_LIBRARY_RELEASE`。后缀包括 `FOUND`、`INCLUDE_DIRS`、`LIBRARY`、`LIBRARY_RELEASE`、`LIBRARY_DEBUG`、`VERSION`、`DLL_RELEASE`、`DLL_DEBUG` 和 `DEPS_LIBRARY`，具体取决于模块和构建。

完整媒体信息工具示例见[仓库 examples](https://github.com/System233/ffmpeg-msvc-prebuilt/tree/main/examples)。
