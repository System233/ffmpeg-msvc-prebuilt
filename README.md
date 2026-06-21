<div align="center">

[English](README.md) | [简体中文](README_CN.md)

[![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-Browse_All_Builds-2ea44f?style=for-the-badge&logo=github)](https://system233.github.io/ffmpeg-msvc-prebuilt/)

# FFmpeg MSVC Prebuilt

Prebuilt FFmpeg binaries for Windows, compiled with MSVC.
Download, extract, and run — no environment setup required.

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

   | Decision | Options |
   |---|---|
   | **Version** | Stable release (7.x, 8.x) or **Master** (latest weekly build) |
   | **License** | **GPL** (includes x264, x265) / **LGPL** (more permissive) |
   | **Linkage** | **Shared** (DLLs, for dev & runtime) / **Static** (single exe, portable) |
   | **Arch** | x64, x86, ARM64, ARM |

3. Download the `.zip` file and extract anywhere

If unsure, pick a **stable shared GPL** variant — it covers most use cases.

---

## Understanding the Artifacts

Each version produces **16 variants** (4 arch × 2 license × 2 linkage).  
Shared variants also include a **develop** archive with debug symbols.

### File naming

```
ffmpeg-8.1.1-r2_x64-windows-shared-gpl.zip         ← binary (runnable + dev files)
ffmpeg-8.1.1-r2_x64-windows-shared-gpl-develop.zip  ← develop (with debug symbols)
         ↑       ↑           ↑      ↑
     version   triplet    linkage license
```

- **Version**: FFmpeg release number (e.g. `8.1.1`) or git describe for Master
- **Revision** (`-r2`): bump count when a version is rebuilt
- **Triplet**: `{arch}-windows` — `x64`, `x86`, `arm64`, `arm`
- **Linkage**: `shared` (DLLs) or `static` (self-contained exe)
- **License**: `gpl` or `lgpl`

### Binary vs Develop (shared only)

| | Binary | Develop |
|---|---|---|
| ffmpeg.exe / ffplay.exe / ffprobe.exe | ✅ | ✅ |
| Headers (`.h`) | ✅ | ✅ |
| Import libraries (`.lib`) + DLLs | ✅ | ✅ |
| pkg-config (`.pc`) + CMake module | ✅ | ✅ |
| PDB debug symbols | ❌ | ✅ |
| Debug libraries (`debug/lib/`) | ❌ | ✅ |
| Archive size | Smaller | Larger |

### Which one to pick?

| I want to... | Download |
|---|---|
| Run FFmpeg commands | **Static Binary** (single exe) or **Shared Binary** |
| Build my own app with FFmpeg | **Shared Binary** (headers + libs) |
| Debug my app with FFmpeg symbols | **Shared Develop** (includes PDB) |
| Carry one exe, no DLLs | **Static Binary** |

**Static** variants contain only executables — no headers, no import libraries.

---

## What's Included

### Binary (all linkage types)

- **CLI tools**: `ffmpeg.exe`, `ffplay.exe`, `ffprobe.exe`
- **Development files** (shared only): headers (`.h`), import libraries (`.lib`), DLLs
- **Integration** (shared only): pkg-config files (`.pc`), CMake `FindFFMPEG.cmake`
- **Metadata**: `BUILD_INFO`, `CONTROL`, `LICENSE.txt`
- All dependencies are statically linked or bundled — **zero runtime DLLs to install**

### Develop (shared only, adds to binary)

- **PDB symbol files** for all executables and DLLs
- **Debug build libraries** under `debug/lib/`

### Static

- Self-contained executables only — no external DLLs needed at runtime

---

## Integration Example — ffmeta

The [`examples/`](./examples/) directory contains `ffmeta`, a command-line media metadata viewer built with FFmpeg. It demonstrates three ways to link against a **shared** prebuilt distribution.

Extract a shared binary or develop archive, then point your build system to the extracted prefix:

```bash
# Extract first, then build
cmake -B build -DFFMPEG_ROOT=C:/path/to/extracted_prefix
cmake --build build
```

See [`examples/README.md`](./examples/README.md) for CMake, Meson, and GNU Make instructions.

---

## Key Features

- **MSVC compiled** — native Windows compatibility with optimal performance
- **Multi-architecture** — x64, x86, ARM, ARM64
- **Weekly master builds** — tracks the latest FFmpeg development branch
- **Automated upstream detection** — new releases are automatically detected and built
- **LTS maintenance** — stable versions with long-term support

---

## License

- Repository scripts and configuration: **MIT License**
- FFmpeg and its dependencies: **GPL** / **LGPL** (varies by variant)

---

<div align="center">

Questions? [Open an issue](https://github.com/System233/ffmpeg-msvc-prebuilt/issues)

</div>
