# Update history

## 2026-11-27

- Added licensing risk notices to historical LGPL builds.

## 2026-11-26

- Replaced complete Shared Develop archives with differential Debug add-ons to reduce duplicate distribution.
- Added SDK integration tests and debug symbol matching checks.
- Reworked automated build repair to improve failure diagnosis and repair strategies.

## 2026-11-25

- Reworked the build and publication system to support independent builds of multiple versions, incremental builds and dependency reuse based on native vcpkg ABIs.
- Added license compatibility and publication artifact checks, with third-party copyright notices and SPDX dependency information for build artifacts.

## 2026-11-22

### Legacy LGPL builds

- **LAME / MPGLIB:** Analysis of the companion PDB for the released FFmpeg 8.1.3 x64 Shared LGPL avcodec DLL identified MPGLIB object contributions. LAME identifies this decoder as GPL. The change excludes the unnecessary decoder introduced through `libmpghip-static.lib` while retaining MP3 encoding.
- **Lensfun:** Corrected the FFmpeg lensfun filter's license classification, restricting it to GPL builds.
- **FFmpeg 3.4 / OpenSSL:** Historical 3.4.14 LGPL metadata lists the nonfree feature. The change excludes the OpenSSL feature explicitly requiring nonfree for that version.
- **LAME `fft.c`:** Historical rights notices await upstream clarification.

The remaining historical LGPL archives await individual verification. See [Licenses and redistribution](../licenses/).

## 2026-11-20

- Added FFmpeg 9.1 build support.

## 2026-11-06

- Fixed commit reference resolution when downloading Master source code.

## 2026-11-05

- Fixed static operation table generation during Master ARM64 cross-compilation.

## 2026-10-23

- Adapted Master builds to the removal of the OpenGL configuration option.

## 2026-09-21

- Added FFmpeg 8.1.3 build support.

## 2026-09-19

- Added FFmpeg 9.0.2 build support.

## 2026-08-12

- Added FFmpeg 9.0.1 build support.

## 2026-06-23

- Added FFmpeg compilation and linking integration tests.

## 2026-06-22

- Added FFmpeg 4.4.8, 5.1.7, 5.1.9, 5.1.10 and 6.1.6 build support.
- Introduced automated build repair.

## 2026-06-21

- Migrated the build pipeline to a vcpkg-based build system.
- Added FFmpeg 7.1.5 and 8.1.2 build support.
