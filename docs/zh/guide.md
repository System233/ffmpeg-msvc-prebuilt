# 使用指南

## 快速开始

从[下载页](../)选择适合目标系统的稳定版本和架构，下载 **二进制（Binary）** ZIP。一般选择共享库；仅需要独立命令行程序时可选择静态库。GPL/LGPL 选型参见[许可证说明](../licenses/#选择许可证)。

### 下载完整性校验

在下载项的信息面板复制 SHA-256，在 PowerShell 中校验原始 ZIP：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\ffmpeg.zip"
```

将文件名替换为实际下载的 ZIP。Hash 必须与对应下载项记录一致（不区分大小写）；不一致时不要使用，重新下载。没有记录哈希的旧包无法通过此方法确认一致性。哈希校验不是数字签名验证。

## 安装与基本命令

1. 解压 ZIP 至固定目录，例如 `C:\Tools\ffmpeg`。
2. 找到 `ffmpeg.exe` 所在目录：共享库通常在 `bin/`，静态库通常在解压根目录。
3. 将该目录添加到 Windows 用户 PATH，重新打开 PowerShell。共享库的 DLL 应保留在 EXE 旁。

先验证安装：

```powershell
Get-Command ffmpeg
ffmpeg -version
ffprobe -version
```

确认路径、版本与下载的构建一致，再执行以下命令（将文件名替换为实际媒体文件）：

```powershell
# 查看媒体信息
ffprobe -hide_banner input.mp4

# 转封装（无需重新编码，要求容器兼容）
ffmpeg -i input.mp4 -c copy output.mkv

# 转码
ffmpeg -i input.mp4 output.webm
```

不修改 PATH 也可以在可执行文件所在目录运行 `.\ffmpeg.exe -version`，或使用完整路径。

## 如何选择？

| 需求 | 下载 |
|---|---|
| 日常命令行使用 | 共享库二进制 |
| 独立 EXE，无需 FFmpeg DLL | 静态库二进制 |
| C/C++ 应用开发 | 共享库二进制 |
| FFmpeg 调试库及 PDB | 共享库二进制 + 对应调试库 |

架构应与运行环境或目标应用匹配：x64、x86、ARM64 或 ARM。稳定版本适合日常使用；快照版本适合测试上游新功能。已有项目应优先匹配所需版本。

## 进一步阅读

- [开发集成](../integration/)：将 FFmpeg 库链接到自己的应用。
- [构建产物](../packages/)：目录、调试库、文件命名与兼容性。
- [许可证与再分发](../licenses/)：选择 GPL/LGPL 及分发注意事项。
- [自行构建指南](../self-build/)：定制功能或从源码生成 SDK。
