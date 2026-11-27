## Which FFmpeg version should I choose?

For a new installation, start with Shared Binary from the latest release. For an existing application, match its required FFmpeg major or exact version rather than upgrading blindly.


- **Stable versions:** for daily use, production and reproducible deployments.
- **LTS:** use the newest available patch in the required long-term support family. The label is a catalog classification and does not guarantee current upstream maintenance.
- **Snapshots:** for recent upstream features and fixes; APIs and behavior may change.

Match the architecture to the target: x64 for typical 64-bit Intel/AMD Windows, ARM64 for native Windows on Arm, and x86 or ARM only when a 32-bit target requires it. See the [quick start](/guide/#quick-start) for all build options.

## What is the difference between Shared and Static?

Shared is the usual choice. Static is intended for single-executable deployments.


- **Shared (recommended):** includes executables, DLLs, headers and import libraries. Keep the matching DLLs at runtime and use the corresponding headers and .lib files when compiling.
- **Static:** executables such as ffmpeg.exe and ffprobe.exe do not need separate FFmpeg DLLs. No application-linkable SDK is included.

A complete static SDK would include many third-party static libraries and be too large to distribute. Build from source for static linking. See the [package selection table](/guide/#which-one-to-pick) and [integration prerequisites](/integration/#prerequisites).

## What is the difference between GPL and LGPL?

GPL builds offer more optional components; LGPL builds suit projects that require LGPL libraries.


- **GPL:** may include GPL encoders such as x264 and x265, for workflows that require those encoders.
- **LGPL:** updated builds restrict GPL components; historical LGPL builds have disclosed licensing risks.

Run `ffmpeg -encoders` to check for required encoders. The archives include license notices and dependency information. See [licenses and redistribution](/licenses/#choosing-a-license).

## How do I install and use FFmpeg?

Extract the binary archive and add its executable directory to PATH to run FFmpeg from a terminal.


1. Prefer the Shared Binary ZIP and extract it to a permanent directory, e.g. `C:\Tools\ffmpeg`.
2. Find the directory containing ffmpeg.exe: typically `bin` for Shared, or the extraction root for Static.
3. Add that directory to your Windows user PATH and reopen the terminal.

```powershell
ffmpeg -version
ffprobe -hide_banner input.mp4
ffmpeg -i input.mp4 output.mkv
```

These commands verify installation, inspect a media file and transcode it. Keep matching DLLs next to Shared executables. You can also run the tools directly from their directory without changing PATH. See [installation and first commands](/guide/#installation-and-first-commands).

## How do I use FFmpeg in my application?

Link your application against the import libraries and headers from Shared Binary. Choose the matching target architecture and set `FFMPEG_ROOT` to the extracted directory and use its supplied CMake module:

```cmake
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
find_package(FFmpeg MODULE REQUIRED)
target_link_libraries(myapp PRIVATE FFmpeg::FFmpeg)
```

Here myapp is an existing CMake target. Configure with `-DFFMPEG_ROOT=C:/Tools/ffmpeg` and make the matching DLLs available at runtime. Without CMake, configure include, lib and runtime DLL paths manually. See the [complete CMake example](/integration/#minimal-version) and [automatic DLL deployment](/integration/#with-dll-deployment-windows-shared-builds).

## How do I use debug libraries?

Extract Debug over the matching Binary to use debug libraries and symbols. Normal execution and Release development do not require Debug.


1. Download Binary and Debug from the same release batch, architecture, linkage and license.
2. Extract both ZIPs into the same directory, retaining their directory structure. If the release offers Develop instead, use that complete archive.
3. Use import libraries under `debug/lib` and DLLs under `debug/bin` for Debug builds. Release DLL PDBs are under `bin`. In Visual Studio, verify symbols match loaded modules.

Do not mix PDBs or Debug/Release DLLs from unrelated builds. See [debug archive contents](/packages/#debug-shared-only-requires-binary) and [debug builds and symbols](/integration/#debug-builds-and-symbols).

## How do I verify a downloaded file?

Compare the downloaded ZIP's SHA-256 with the catalog digest. Open the information button to find the recorded hash, then calculate it in PowerShell before extracting:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\ffmpeg.zip"
```

Replace the example filename with the actual ZIP name. Compare the Hash value with the catalog (case-insensitive). If they differ, do not use the file; download it again and verify. SHA-256 checks consistency with the recorded file, not a digital signature. See [verifying downloads](/guide/#verifying-downloads).
