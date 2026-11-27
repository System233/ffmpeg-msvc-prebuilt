# Guide

## Quick start

Choose a stable version and the target architecture on the [download page](../), then download the **Binary** ZIP. Shared is the usual choice; choose Static when you need standalone command-line executables. See [license selection](../licenses/#choosing-a-license) for GPL/LGPL.

### Verifying downloads

Copy the SHA-256 from the download information panel, then hash the original ZIP in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\ffmpeg.zip"
```

Replace the filename with the actual ZIP. The hash must match the corresponding download record (case-insensitive). If it differs, do not use the file; download it again. Older archives without a recorded hash cannot be checked this way. This is not digital-signature verification.

## Installation and first commands

1. Extract the ZIP to a permanent directory, such as `C:\Tools\ffmpeg`.
2. Locate `ffmpeg.exe`: typically in `bin/` for Shared, or the extraction root for Static.
3. Add that directory to the Windows user PATH and reopen PowerShell. Keep the matching Shared DLLs next to the executables.

Verify your installation first:

```powershell
Get-Command ffmpeg
ffmpeg -version
ffprobe -version
```

Confirm the path and version match the downloaded build, then run these commands with your actual media filenames:

```powershell
# Inspect media
ffprobe -hide_banner input.mp4

# Remux without re-encoding (requires compatible container)
ffmpeg -i input.mp4 -c copy output.mkv

# Transcode
ffmpeg -i input.mp4 output.webm
```

Without changing PATH, run `.\ffmpeg.exe -version` from its directory or use its full path.

## Which one to pick?

| I want to... | Download |
|---|---|
| Run FFmpeg commands | Shared Binary |
| Use standalone executables without FFmpeg DLLs | Static Binary |
| Develop a C/C++ application | Shared Binary |
| Debug FFmpeg with libraries and PDBs | Shared Binary + matching Debug |

Match the architecture to your system or target application: x64, x86, ARM64 or ARM. Stable releases suit everyday use; snapshots are for testing upstream changes. For existing projects, match the required version first.

## Further reading

- [Integration](../integration/): link FFmpeg libraries into your application.
- [Build artifacts](../packages/): layouts, Debug, filenames and compatibility.
- [Licenses and redistribution](../licenses/): choosing GPL/LGPL and distribution considerations.
- [Self-build guide](../self-build/): customize features or build an SDK from source.
