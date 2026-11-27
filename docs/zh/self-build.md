---
title: 自行构建
description: 使用本项目的 FFmpeg 构建工具和 vcpkg，在 Windows 上从源码生成 MSVC 版本。
---

# 自行构建

预构建版本适用于一般使用。需要定制组件、修改源码或在本地生成 SDK 时，可以使用本项目的构建工具。它将版本配置转换为 vcpkg overlay port，由 vcpkg 管理依赖、编译和二进制缓存。

## 环境准备

- Windows，Visual Studio 或 Visual Studio Build Tools，安装“使用 C++ 的桌面开发”工作负载及 Windows SDK。构建 ARM 或 ARM64 时还需要对应的 MSVC 工具集。
- Git、Python 3.11 或更新版本、PowerShell。
- 可访问 FFmpeg 源码及 vcpkg 依赖下载源，并预留足够的磁盘空间。首次编译需要构建依赖，后续可复用 vcpkg 缓存。

建议使用独立的 vcpkg 安装目录，以免与其他项目或 FFmpeg 版本相互影响。

## 获取构建工具

在 PowerShell 中执行：

```powershell
git clone https://github.com/System233/ffmpeg-msvc-prebuilt.git
cd ffmpeg-msvc-prebuilt
python -m pip install -e .
```

构建工具以当前源码仓库为基础，使用其中的版本配置、补丁、端口及 CMake 模板。若需要复现某次发布，先切换到该发布所对应的项目提交，再安装构建工具。

## 准备 vcpkg

以下示例采用项目 CI 使用的 vcpkg 2026.06.01。其他项目提交可能使用不同的固定版本。

```powershell
$env:VCPKG_ROOT = Join-Path (Get-Location) "_work/vcpkg-local"
git clone --branch 2026.06.01 --depth 1 https://github.com/microsoft/vcpkg.git $env:VCPKG_ROOT
& "$env:VCPKG_ROOT/bootstrap-vcpkg.bat"
```

如果已经准备好兼容的 vcpkg，只需设置 `VCPKG_ROOT` 为其目录，或设置 `FFVCPKG_BIN` 为 vcpkg 可执行文件的完整路径。

## 构建指定版本

以 FFmpeg 8.1.3、x64、共享库、GPL 为例。先生成对应版本的端口，再执行安装：

```powershell
python -m ffbuild generate 8.1.3
python -m ffvcpkg install "ffmpeg[all-gpl]" `
  --triplet=x64-windows `
  --overlay-ports=_work/ffbuild/generated-ports/ffmpeg-8-1-3 `
  --overlay-ports=ports
```

`ffbuild generate` 根据仓库内的版本配置生成端口，并不编译 FFmpeg。`ffvcpkg install` 调用原生 vcpkg 安装流程，自动使用本项目的自定义 triplet。

版本化目录用于选择源码版本，但生成端口的包名仍是 `ffmpeg`。不能将整个 generated-ports 父目录当作 overlay，也不能在同一个 triplet 安装树中同时安装多个 FFmpeg 版本。切换版本时建议使用独立安装树。

## 选择构建变体

将上述命令中的 package spec 和 triplet 替换为所需组合：

| 选项 | Package spec |
| --- | --- |
| 共享库 GPL（推荐） | `ffmpeg[all-gpl]` |
| 共享库 LGPL | `ffmpeg[all-lgpl]` |
| 静态库 GPL | `ffmpeg[all-gpl,static]` |
| 静态库 LGPL | `ffmpeg[all-lgpl,static]` |

支持的 triplet：`x64-windows`、`x86-windows`、`arm64-windows`、`arm-windows`。一般选择共享库；需要静态链接 SDK 或独立可执行文件时选择静态库。

如需定制组件，参见 [构建特性参考](../reference/) 及仓库中的版本配置。特性可用性随源码版本和架构变化。

## 构建快照版本

项目支持固定上游提交后构建快照。以下命令发现上游 HEAD，并生成包含快照的端口集合，同时记录固定源码信息：

```powershell
python -m ffbuild generate --all --include-master --master-snapshot-file snapshot.json
python -m ffvcpkg install "ffmpeg[all-gpl]" `
  --triplet=x64-windows `
  --overlay-ports=_work/ffbuild/generated-ports/ffmpeg-master `
  --overlay-ports=ports
```

若要复现某次快照，可使用 `--describe`、`--commit`、`--sha512` 指定该构建的源码标识、完整提交及源归档校验值。

## 使用构建结果

默认 vcpkg 安装树位于 `$env:VCPKG_ROOT/installed/<triplet>/`。本项目的 vcpkg 端口将命令行工具安装到 `tools/ffmpeg/`，共享库和 SDK 位于 `bin/`、`lib/`、`include/` 等目录。

```powershell
& "$env:VCPKG_ROOT/installed/x64-windows/tools/ffmpeg/ffmpeg.exe" -version
```

对于共享库 构建，将对应安装前缀传给 CMake 的 `FFMPEG_ROOT` 即可使用 SDK，见 [开发集成](../integration/)。

上述命令用于本地构建与安装，不会生成 GitHub Release 或自动上传任何产物。公开 ZIP 的差分打包、验证和发布是独立流程，详细实现见 [项目构建工具文档](https://github.com/System233/ffmpeg-msvc-prebuilt/blob/main/docs/build-tools.md)。
