---
title: Guide
description: How to choose and use prebuilt FFmpeg binaries for Windows with MSVC — understand variants, file naming, and what's included.
---

# Guide

## Quick Start

1. Visit the [GitHub Pages site](https://system233.github.io/ffmpeg-msvc-prebuilt/) or [Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)
2. Choose your variant:

   | Decision | Options |
   |---|---|
   | **Version** | Stable release (7.x, 8.x) or **Master** (latest weekly build) |
   | **License** | **GPL** (includes x264, x265) / **LGPL** (more permissive) |
   | **Linkage** | **Shared** (DLLs, for dev & runtime) / **Static** (single exe, portable) |
   | **Arch** | x64, x86, ARM64, ARM |

3. Download the `.zip` file and extract anywhere

If unsure, pick a **stable shared GPL** variant — it covers most use cases.

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
