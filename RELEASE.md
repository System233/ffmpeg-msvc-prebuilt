This release contains FFmpeg builds, compiled with MSVC (Microsoft Visual C++) via GitHub Actions, and organized as follows:

- **Variants**: Includes both **shared** and **static** builds.
- **Architectures**: Each variant is available for **amd64**, **x86**, **arm**, and **arm64**.
- **Licenses**:
  - **GPL**: Includes GPL components such as the **x264** and **x265** encoders.
  - **LGPL**: Excludes GPL-licensed components.

#### Included Dependencies

- [nv-codec-headers](https://github.com/FFmpeg/nv-codec-headers.git)
- [zlib](https://github.com/madler/zlib.git)
- [libjxl](https://github.com/libjxl/libjxl.git)
  - [openexr](https://github.com/AcademySoftwareFoundation/openexr.git)
- [freetype](https://gitlab.freedesktop.org/freetype/freetype.git)
- [harfbuzz](https://github.com/harfbuzz/harfbuzz.git)
- [SDL2](https://github.com/libsdl-org/SDL.git)
- [x264](https://code.videolan.org/videolan/x264.git) (GPL builds only)
- [x265](https://bitbucket.org/multicoreware/x265_git.git) (GPL builds only)

#### Release Notes