---
title: Build from source
description: Build FFmpeg with MSVC on Windows using the project's build tools and vcpkg.
---

# Build from source

Use prebuilt archives for general use. For custom features, source changes or a locally built SDK, use the project's build tools. They convert version configurations into vcpkg overlay ports; vcpkg manages dependencies, compilation and its binary cache.

## Prerequisites

- Windows with Visual Studio or Visual Studio Build Tools, the Desktop development with C++ workload and Windows SDK. ARM/ARM64 builds require the corresponding MSVC toolsets.
- Git, Python 3.11 or later, and PowerShell.
- Access to FFmpeg source and vcpkg dependency downloads, plus sufficient disk space. The initial build compiles dependencies; later builds can reuse the vcpkg cache.

Use an isolated vcpkg installation to avoid interfering with other projects or FFmpeg versions.

## Get the build tools

Run in PowerShell:

```powershell
git clone https://github.com/System233/ffmpeg-msvc-prebuilt.git
cd ffmpeg-msvc-prebuilt
python -m pip install -e .
```

The tools use version configurations, patches, ports and CMake templates from the source checkout. To reproduce a particular release, check out its corresponding project commit before installing the tools.

## Prepare vcpkg

This example uses vcpkg 2026.06.01, the version pinned by the project's CI. Other project commits may use a different pin.

```powershell
$env:VCPKG_ROOT = Join-Path (Get-Location) "_work/vcpkg-local"
git clone --branch 2026.06.01 --depth 1 https://github.com/microsoft/vcpkg.git $env:VCPKG_ROOT
& "$env:VCPKG_ROOT/bootstrap-vcpkg.bat"
```

If you already have compatible vcpkg tooling, set `VCPKG_ROOT` to its directory or `FFVCPKG_BIN` to the full executable path.

## Build a selected version

This example builds FFmpeg 8.1.3, x64, Shared, GPL. Generate the selected port and install it:

```powershell
python -m ffbuild generate 8.1.3
python -m ffvcpkg install "ffmpeg[all-gpl]" `
  --triplet=x64-windows `
  --overlay-ports=_work/ffbuild/generated-ports/ffmpeg-8-1-3 `
  --overlay-ports=ports
```

`ffbuild generate` creates the overlay port from the repository's version configuration without compiling FFmpeg. `ffvcpkg install` invokes native vcpkg with the project's custom triplets.

The version-qualified directory selects the source version, but the package identity remains `ffmpeg`. Never use the entire generated-ports parent as an overlay. Multiple FFmpeg versions cannot coexist in the same installed triplet tree; use isolated install trees when switching versions.

## Choose a build variant

Replace the package spec and triplet in the command as needed:

| Option | Package spec |
| --- | --- |
| Shared GPL (recommended) | `ffmpeg[all-gpl]` |
| Shared LGPL | `ffmpeg[all-lgpl]` |
| Static GPL | `ffmpeg[all-gpl,static]` |
| Static LGPL | `ffmpeg[all-lgpl,static]` |

Supported triplets: `x64-windows`, `x86-windows`, `arm64-windows`, and `arm-windows`. Shared is the usual choice. Static is intended for standalone executable deployments.

For custom components, see the [feature reference](../reference/) and the repository's version configurations. Feature availability varies by source version and architecture.

## Build a snapshot

The project supports building snapshots pinned to upstream commits. The following generates the port set including upstream HEAD and records its pinned source metadata:

```powershell
python -m ffbuild generate --all --include-master --master-snapshot-file snapshot.json
python -m ffvcpkg install "ffmpeg[all-gpl]" `
  --triplet=x64-windows `
  --overlay-ports=_work/ffbuild/generated-ports/ffmpeg-master `
  --overlay-ports=ports
```

To reproduce a particular snapshot, use `--describe`, `--commit`, and `--sha512` to specify its source identifier, full commit and source archive checksum.

## Use the build results

The default installed tree is under `$env:VCPKG_ROOT/installed/<triplet>/`. The project's port installs command-line tools under `tools/ffmpeg/`; shared libraries and SDK files are in directories such as `bin/`, `lib/`, and `include/`.

```powershell
& "$env:VCPKG_ROOT/installed/x64-windows/tools/ffmpeg/ffmpeg.exe" -version
```

For Shared builds, pass the installation prefix as CMake's `FFMPEG_ROOT` to use the SDK. See [application integration](../integration/).

These commands build and install locally. They do not create a GitHub Release or upload artifacts. Public ZIP packaging, validation and publication are separate steps; see the [project build tooling documentation](https://github.com/System233/ffmpeg-msvc-prebuilt/blob/main/docs/build-tools.md).
