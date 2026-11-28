<div align="center">

[English](README.md) | [简体中文](README_CN.md)

[![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-Browse_All_Builds-2ea44f?style=for-the-badge&logo=github)](https://system233.github.io/ffmpeg-msvc-prebuilt/)

# FFmpeg MSVC Prebuilt

Prebuilt FFmpeg binaries for Windows, compiled with MSVC.
Download, extract, and run — no environment setup required.

[![Build](https://img.shields.io/github/actions/workflow/status/System233/ffmpeg-msvc-prebuilt/build-release.yml?label=Build&logo=github)](https://github.com/System233/ffmpeg-msvc-prebuilt/actions/workflows/build-release.yml)
[![Master](https://img.shields.io/github/actions/workflow/status/System233/ffmpeg-msvc-prebuilt/master-build.yml?label=Master&logo=github)](https://github.com/System233/ffmpeg-msvc-prebuilt/actions/workflows/master-build.yml)
[![Pages](https://img.shields.io/github/actions/workflow/status/System233/ffmpeg-msvc-prebuilt/pages.yml?branch=web&label=Pages&logo=github)](https://github.com/System233/ffmpeg-msvc-prebuilt/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/v/release/System233/ffmpeg-msvc-prebuilt?display_name=tag&label=Release)](https://github.com/System233/ffmpeg-msvc-prebuilt/releases/latest)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20GPL%20%2F%20LGPL-blue)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/System233/ffmpeg-msvc-prebuilt)](https://github.com/System233/ffmpeg-msvc-prebuilt/commits/main)

</div>

---

## 🚀 Browse Prebuilt Binaries

**[https://system233.github.io/ffmpeg-msvc-prebuilt/](https://system233.github.io/ffmpeg-msvc-prebuilt/)**

Search all releases by version, filter by architecture or license, and download directly — no CLI or GitHub account needed.

Alternatively, download directly from **[GitHub Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)**.

---

## Quick Start

1. Open the [GitHub Pages site](https://system233.github.io/ffmpeg-msvc-prebuilt/) or [Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
2. Choose your variant:

   | Decision    | Options                                                                  |
   | ----------- | ------------------------------------------------------------------------ |
   | **Version** | Stable release (7.x, 8.x) or **Master** (latest weekly build)            |
   | **License** | **GPL** (includes x264, x265) / **LGPL** (more permissive)               |
   | **Linkage** | **Shared** (DLLs, for dev & runtime) / **Static** (single exe, portable) |
   | **Arch**    | x64, x86, ARM64, ARM                                                     |

3. Download the `.zip` file and extract anywhere

If unsure, pick a **stable shared GPL** variant — it covers most use cases.

---

## Understanding the Artifacts

Each version produces **16 variants** (4 arch × 2 license × 2 linkage).  
Shared variants also include a **debug** add-on archive with debug libraries and symbols; extract it over the matching Binary.

### File naming

```
ffmpeg-9.1_x64-windows-static-lgpl-261125.zip
ffmpeg-9.1_arm64-windows-shared-gpl-261125.zip
ffmpeg-9.1_arm64-windows-shared-gpl-debug-261125.zip
ffmpeg-master_x64-windows-static-gpl-261125.zip
```

Dates use UTC YYMMDD, fixed once by the plan. No ABI, Revision, or packaging format suffix appears in public filenames. Release tags use version and date, e.g. `ffmpeg-9.1-261125` (same-day batches use R2, R3, etc.). Tags are created after verification, not as build triggers. Full native ABI and archive SHA-256 remain in the data branch. Incremental publication reuses unchanged ZIPs with their original filename/date and digest; history is immutable.

A complete standard matrix publishes only 24 ZIPs (8 Static, 8 Shared, 8 Debug). All license evidence for redistribution is collected in `share/ffmpeg/copyright` and `share/ffmpeg/sbom.spdx.json`, with the primary license in `LICENSE.txt`. Build provenance and original dependency evidence remain outside the public ZIP. Corresponding source obligations remain separate.

### Binary vs Debug Add-on (shared only)

|                                       | Binary  | Debug Add-on |
| ------------------------------------- | ------- | ------- |
| ffmpeg.exe / ffplay.exe / ffprobe.exe | ✅       | ❌ |
| Headers (`.h`)                        | ✅       | ❌ |
| Import libraries (`.lib`) + DLLs      | ✅       | ❌ |
| pkg-config (`.pc`) + CMake module     | ✅       | ❌ |
| FFmpeg DLL PDB debug symbols          | ❌       | ✅       |
| Debug libraries (`debug/lib/`)        | ❌       | ✅       |
| Archive size                          | Smaller | Larger  |

### Which one to pick?

| I want to...                     | Download                                            |
| -------------------------------- | --------------------------------------------------- |
| Run FFmpeg commands              | **Static Binary** (single exe) or **Shared Binary** |
| Build my own app with FFmpeg     | **Shared Binary** (headers + libs)                  |
| Debug my app with FFmpeg symbols | **Shared Binary + Debug Add-on** (includes PDB)                   |
| Carry one exe, no DLLs           | **Static Binary**                                   |

**Static** variants contain executables and lightweight license/SPDX files,
but no headers or imported/static libraries.
The Shared SDK is for dynamic linking with the provided import libraries and DLLs only.
Private third-party static libraries are not distributed; `pkg-config --static` does not make this a static SDK.

---

## What's Included

### Binary (all linkage types)

- **CLI tools**: `ffmpeg.exe`, `ffplay.exe`, `ffprobe.exe`
- **Development files** (shared only): headers (`.h`), import libraries (`.lib`), DLLs
- **Integration** (shared only): pkg-config files (`.pc`), CMake `FindFFmpeg.cmake`
- **Licenses**: `LICENSE.txt`, combined `share/ffmpeg/copyright`
- **SBOM**: `share/ffmpeg/sbom.spdx.json` (SPDX 2.3)
- `share/` contains only the FFmpeg package namespace; native vcpkg metadata
  and original dependency SPDX are retained as audit evidence outside the ZIP.
- No extra third-party runtime DLL deployment is intended; normal Windows
  operating-system DLLs are still required.

### Debug Add-on (shared only, requires Binary)

New format v2 archives are differential. Historical Develop archives remain standalone.

- **PDB symbol files** for FFmpeg release/debug DLLs; CLI executable PDBs are included only when available and matched.
- **Debug build libraries** under `debug/lib/` and debug DLLs under `debug/bin/`.

### Static

- Self-contained executables plus compliance metadata — no external FFmpeg
  DLLs needed at runtime

The SPDX document describes the **installed vcpkg dependency graph**, not an
object-file-level link map. The `lgpl`/`gpl` filename is FFmpeg's configured
license mode, **not** proof that every third-party redistribution obligation is
satisfied. Source availability, applicable notices, and LGPL relinking
obligations must still be evaluated before downstream redistribution.

---

## Integration Example — ffmeta

The [`examples/`](./examples/) directory contains `ffmeta`, a command-line media metadata viewer built with FFmpeg. It demonstrates three ways to link against a **shared** prebuilt distribution.

Extract a shared Binary archive (optionally overlay its matching Debug Add-on), then point your build system to the extracted prefix:

```bash
# Extract first, then build
cmake -B build -DCMAKE_PREFIX_PATH=C:/path/to/extracted_prefix
cmake --build build
```

For older SDKs without Config Mode, use `-DFFMPEG_ROOT=...` instead.

See [`examples/README.md`](./examples/README.md) for CMake, Meson, and GNU Make instructions.

---

## Key Features

- **MSVC compiled** — native Windows compatibility with optimal performance
- **Multi-architecture** — x64, x86, ARM, ARM64
- **Weekly master builds** — tracks the latest FFmpeg development branch
- **Automated upstream detection** — new upstream releases receive version-scoped validation PRs
- **LTS maintenance** — stable versions with long-term support

---

## License

- Repository scripts and configuration: **MIT License**
- FFmpeg and its dependencies: **GPL** / **LGPL** (varies by variant)

---

<div align="center">

Questions? [Open an issue](https://github.com/System233/ffmpeg-msvc-prebuilt/issues)

</div>
