# FFmpeg GitHub Action Builds (MSVC)

This repository provides **FFmpeg builds** compiled with **MSVC (Microsoft Visual C++)**, leveraging GitHub Actions to automate the process. Each release includes complete precompiled binaries, libraries, and development files, optimized for various platforms and configurations.

[![Build FFmpeg](https://github.com/System233/ffmpeg-builds/actions/workflows/build.yml/badge.svg?event=push)](https://github.com/System233/ffmpeg-builds/actions/workflows/build.yml)

## Contents of the Release Packages

Each release provides the following for all build variants, architectures, and licenses:

1. **Precompiled binaries** (`ffmpeg`, `ffplay`, `ffprobe`, etc.).
2. **Dynamic and static libraries** for FFmpeg and included dependencies.
3. **Header files** for development.
4. **pkg-config (.pc) files** for library integration.
5. **CMake configuration files** for easy integration with CMake-based projects.
6. **SHA1 checksum files** for verifying integrity.

The files are packaged into **.zip** archives for each configuration, making it easy to download and integrate into your workflow.

## Downloading and Using the Builds

1. Visit the **[Releases](https://github.com/System233/ffmpeg-msvc-prebuilt/releases)** section.
2. Download the `.zip` archive and its corresponding `.sha1` checksum file for your desired configuration.
3. Verify the archive integrity using the `.sha1` checksum file.
   ```sh
   sha1sum -c <filename>.sha1
   ```
4. Extract the archive to access binaries, libraries, and development files.

## Features

### Built with MSVC

- Ensures compatibility with Windows development environments.
- Generates high-performance binaries optimized for modern Windows platforms.

### Build Variants

- **Shared**: Includes dynamic libraries and runtime dependencies.
- **Static**: Fully self-contained binaries for standalone usage.

### Supported Architectures

- **amd64** (x86_64)
- **x86** (32-bit)
- **arm** (armv7l)
- **arm64** (aarch64)

### Licensing Options

- **GPL Builds**: Includes additional components like **x264** and **x265** encoders.
- **LGPL Builds**: Excludes GPL-licensed components for more permissive licensing.

### Included Dependencies

All builds include the following libraries:

- [nv-codec-headers](https://github.com/FFmpeg/nv-codec-headers.git)
- [zlib](https://github.com/madler/zlib.git)
- [libjxl](https://github.com/libjxl/libjxl.git)
  - [openexr](https://github.com/AcademySoftwareFoundation/openexr.git)
- [freetype](https://gitlab.freedesktop.org/freetype/freetype.git)
- [harfbuzz](https://github.com/harfbuzz/harfbuzz.git)
- [libass](https://github.com/libass/libass.git)
  - [fribidi](https://github.com/fribidi/fribidi.git)
- [SDL2](https://github.com/libsdl-org/SDL.git)
- [libvpx](https://github.com/webmproject/libvpx.git)
- [libwebp](https://github.com/webmproject/libwebp.git)
- [x264](https://code.videolan.org/videolan/x264.git) (GPL builds only)
- [x265](https://bitbucket.org/multicoreware/x265_git.git) (GPL builds only)


## License

- The scripts in this repository are licensed under the **MIT License**.
- The binaries inherit the licensing terms of FFmpeg and its dependencies, which may include **GPL** or **LGPL**.
