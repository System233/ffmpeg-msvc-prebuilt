## 如何选择 FFmpeg 版本？

首次使用建议选择最新稳定版本的共享库 二进制包。需要与已有项目保持兼容时，应选择项目要求的 FFmpeg 主版本或具体版本，不要仅凭版本号越新越好。


- **稳定版本：** 适合日常使用、生产部署及需要固定版本的项目。
- **LTS：** 适合需要长期支持系列的项目，建议选择该系列最新可用补丁版本；LTS 标记为本项目的版本系列分类，不代表上游仍在维护。
- **快照版本：** 用于体验上游最新功能或修复，接口及行为可能变化。

架构应与运行环境或目标程序匹配：常见 Intel/AMD 64 位 Windows 选择 x64，原生 Windows on Arm 选择 ARM64；仅在目标程序确实需要 32 位库时选择 x86 或 ARM。完整选项见 [快速开始](/guide/#快速开始)。

## 共享库和静态库有什么区别？

一般选择共享库。静态库适用于需要独立可执行文件的场景。


- **共享库（推荐）：** 包含可执行文件、DLL、头文件与导入库。运行时应保留匹配的 DLL，开发时使用对应头文件和 .lib。
- **静态库：** 解压即可运行 ffmpeg.exe、ffprobe.exe 等独立程序，无需另外携带 FFmpeg DLL；不包含供应用链接的 SDK。

完整静态 SDK 包含大量第三方静态库，体积过大，因此仅分发命令行工具；如需静态链接开发，请自行构建。参见 [构建产物选择表](/guide/#如何选择) 与 [开发集成前置条件](/integration/#前置条件)。

## GPL 和 LGPL 有什么区别？

GPL 构建提供更多可选组件，LGPL 构建适用于需要 LGPL 库的项目。


- **GPL：** 可包含 x264、x265 等 GPL 编码器，适合需要这些编码功能的场景。
- **LGPL：** 新版构建限制 GPL 组件；历史 LGPL 构建存在已披露的许可证风险。

可运行 `ffmpeg -encoders` 确认所需编码器是否存在。构建产物包含对应的许可证、版权声明和依赖信息。详见 [许可证与再分发](/licenses/#选择许可证)。

## 如何安装和使用 FFmpeg？

解压二进制包并配置 PATH 后，即可在终端使用 FFmpeg。


1. 优先下载共享库二进制 ZIP，解压至固定目录，例如 `C:\Tools\ffmpeg`。
2. 找到 ffmpeg.exe 所在目录。共享库通常位于 `bin`；静态库 通常位于解压根目录。
3. 将该目录加入 Windows 用户 PATH，重新打开终端。

```powershell
ffmpeg -version
ffprobe -hide_banner input.mp4
ffmpeg -i input.mp4 output.mkv
```

上述命令依次验证安装、检查媒体信息及转码。共享库 构建请保留同目录下匹配的 DLL。若不修改 PATH，也可直接从可执行文件所在目录运行。参见 [安装与基本命令](/guide/#安装与基本命令)。

## 如何在自己的程序中使用 FFmpeg？

使用共享库二进制包中的头文件和导入库即可集成 FFmpeg。选择与目标程序架构一致的构建，将解压目录设为 `FFMPEG_ROOT`，使用随包提供的 CMake 模块：

```cmake
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
find_package(FFmpeg MODULE REQUIRED)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
```

其中 myapp 是已有的 CMake 目标。配置时传入 `-DFFMPEG_ROOT=C:/Tools/ffmpeg`；运行时确保匹配的 DLL 可加载。如果不使用 CMake，则手动设置 include、lib 和运行时 DLL 路径。参见 [完整 CMake 示例](/integration/#最小版本) 及 [DLL 自动部署](/integration/#带-dll-自动部署windows-共享构建)。

## 如何使用调试库？

将调试库与对应二进制包解压至同一目录即可使用。普通运行及 Release 开发不需要额外下载调试库。


1. 下载同一发布批次、架构、链接方式和许可证的二进制与调试库。
2. 将两个 ZIP 解压至同一目录，保留原有目录结构。若该版本提供的是开发版，可直接使用该完整包。
3. 调试构建使用 `debug/lib` 的导入库及 `debug/bin` 的 DLL；Release DLL 对应的 PDB 位于 `bin`。在 Visual Studio 中检查符号是否与已加载模块匹配。

不要混用其他构建的 PDB 或 Debug/Release DLL。详见 [调试库内容](/packages/#调试库仅共享库依赖二进制) 及 [调试构建与符号](/integration/#调试构建与符号)。

## 如何验证下载文件的完整性？

比较下载文件的 SHA-256 与网页记录即可验证完整性。打开下载项旁的信息按钮获取摘要，再使用 PowerShell 计算原始 ZIP 的哈希：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\ffmpeg.zip"
```

将示例文件名替换为实际 ZIP 名称，逐字符比较输出的 Hash 与网页记录（大小写不影响比较）。不一致时不要使用该文件，重新下载并核验。SHA-256 用于验证文件是否与记录一致，不等同于数字签名。参见 [下载完整性校验](/guide/#下载完整性校验)。
