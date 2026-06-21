---
title: 功能参考
---

## Core Libraries

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `avcodec` | `--enable-avcodec` | Build the avcodec library | — | — | — |
| `avdevice` | `--enable-avdevice` | Build the avdevice library | — | — | — |
| `avformat` | `--enable-avformat` | Build the avformat library | — | — | — |
| `avfilter` | `--enable-avfilter` | Build the avfilter library | — | — | — |
| `swresample` | `--enable-swresample` | Build the swresample library | — | — | — |
| `swscale` | `--enable-swscale` | Build the swscale library | — | — | — |
| `avresample` | `--enable-avresample` | Build the avresample library | — | — | `<5.0` |
| `postproc` | `--enable-postproc` | Build the postproc library | `@license-gpl` | — | `<8.0` |

## License Flags

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `license-gpl` | `--enable-gpl` | Allow use of GPL code, the resulting libs and binaries will be under GPL | — | — | — |
| `license-nonfree` | `--enable-nonfree` | Allow use of nonfree code, the resulting libs and binaries will be unredistributable | — | — | — |

## Compression / Text / Fonts

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `zlib` | `--enable-zlib` | zlib support | `zlib` | — | — |
| `bzip2` | `--enable-bzlib` | Bzip2 support | `bzip2` | — | — |
| `lzma` | `--enable-lzma` | lzma support | `liblzma` | — | — |
| `iconv` | `--enable-iconv` | Iconv support | `libiconv` | — | — |
| `freetype` | `--enable-libfreetype` | Needed for drawtext filter | `freetype` | — | — |
| `fribidi` | `--enable-libfribidi` | Improves drawtext filter | `fribidi` | `!uwp` | — |
| `fontconfig` | `--enable-libfontconfig` | Useful for drawtext filter | `fontconfig` | `!uwp` | — |
| `harfbuzz` | `--enable-libharfbuzz` | Enable drawtext filter | `harfbuzz` | `!uwp` | `>=6.1` |
| `ass` | `--enable-libass` | Libass subtitles rendering, needed for subtitles and ass filter support in ffmpeg | `libass` | — | — |

## Audio

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `opus` | `--enable-libopus` | Opus de/encoding via libopus | `opus` | — | — |
| `vorbis` | `--enable-libvorbis` | Vorbis en/decoding via libvorbis, native implementation exists | `libvorbis` | — | — |
| `theora` | `--enable-libtheora` | Theora encoding via libtheora | `libtheora` | — | — |
| `speex` | `--enable-libspeex` | Speex de/encoding via libspeex | `speex` | — | — |
| `mp3lame` | `--enable-libmp3lame` | MP3 encoding via libmp3lame | `mp3lame` | — | — |
| `soxr` | `--enable-libsoxr` | Include libsoxr resampling | `soxr` | — | — |
| `openmpt` | `--enable-libopenmpt` | Decoding tracked files via libopenmpt | `libopenmpt` | — | — |
| `ilbc` | `--enable-libilbc` | iLBC de/encoding via libilbc | `libilbc` | — | — |
| `modplug` | `--enable-libmodplug` | ModPlug via libmodplug | `libmodplug` | `!uwp` | — |
| `tesseract` | `--enable-libtesseract` | Optical character recognition via tesseract | `tesseract` | `!uwp` | — |
| `gme` | `--enable-libgme` | Video game music file de/encoding via libgme | `libgme` | — | — |

## Video / Image

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `dav1d` | `--enable-libdav1d` | AV1 decoding via libdav1d | `dav1d` | — | `>=4.2` |
| `aom` | `--enable-libaom` | AV1 video encoding/decoding via libaom support in ffmpeg | `aom` | `!uwp` | `>=4.0` |
| `vpx` | `--enable-libvpx` | VP8 and VP9 de/encoding via libvpx | `libvpx` | — | — |
| `webp` | `--enable-libwebp` | WebP encoding via libwebp | `libwebp` | — | — |
| `openjpeg` | `--enable-libopenjpeg` | JPEG 2000 de/encoding via OpenJPEG | `openjpeg` | — | `>=4.0` |
| `snappy` | `--enable-libsnappy` | Snappy compression, needed for hap encoding | `snappy` | — | — |
| `openh264` | `--enable-libopenh264` | H.264 de/encoding via openh264 | `openh264` | — | — |
| `lensfun` | `--enable-liblensfun` | Lens correction via lensfun | `lensfun` | `!arm` | `>=4.1` |
| `jxl` | `--enable-libjxl` | JPEG XL de/encoding via libjxl | `libjxl` | — | `>=5.1` |
| `shaderc` | `--enable-libshaderc` | GLSL/Vulkan shader compilation via shaderc (required by libplacebo) | `shaderc` | — | `>=5.0` |
| `svtav1` | `--enable-libsvtav1` | AV1 encoding via SVT-AV1 | `svt-av1` | `!x86 & !arm32 & !uwp` | `>=4.4` |
| `vvenc` | `--enable-libvvenc` | VVC/H.266 encoding via vvenc | `vvenc` | `!x86 & !arm` | `>=7.1` |

## Network / Graphics / Container

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `sdl2` | `--enable-sdl2` | Sdl2 support | `sdl2` | — | — |
| `xml2` | `--enable-libxml2` | XML parsing using the C library libxml2, needed for dash demuxing support | `libxml2` | — | — |
| `srt` | `--enable-libsrt` | Haivision SRT protocol | `libsrt` | `!uwp & !xbox` | `>=4.0` |
| `ssh` | `--enable-libssh` | SFTP protocol via libssh | `libssh` | `!uwp & !xbox` | — |
| `openssl` | `--enable-openssl` | Use OpenSSL for TLS support | `openssl` | — | — |
| `zmq` | `--enable-libzmq` | Enable ZeroMQ support | `zeromq` | `!uwp & !xbox` | — |
| `mysofa` | `--enable-libmysofa` | Spatial audio via libmysofa | `libmysofa` | — | — |
| `bluray` | `--enable-libbluray` | Blu-ray disc support via libbluray | `libbluray` | `!uwp & !xbox` | — |

## Hardware Acceleration

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `nvcodec` | `--enable-cuda --enable-nvenc --enable-ffnvcodec` | Nvidia video decoding/encoding acceleration | `ffnvcodec` | `!uwp & !arm & !arm64` | — |
| `amf` | `--enable-amf` | AMD AMF codec support | `amd-amf` | — | `>=4.0` |
| `qsv` | `--enable-libvpl` | Intel QSV Codec via oneVPL | `libvpl` | `!uwp & !arm & !arm64` | `>=6.0` |
| `mfx` | `--enable-libmfx` | Intel QSV Codec via libmfx (pre-8.0) | `mfx-dispatch` | `!uwp & !arm & !arm64` | `<8.0` |
| `vulkan` | `--enable-vulkan` | H.264, HEVC and AV1 de/encoding via Vulkan | `vulkan` | `!uwp & !xbox` | `>=7.0` |
| `opencl` | `--enable-opencl` | OpenCL processing | `opencl` | `!uwp` | — |
| `opengl` | `--enable-opengl` | OpenGL rendering | `opengl` | `!uwp & !xbox` | — |

## Windows Platform

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `w32threads` | `--enable-w32threads` | Windows thread support | — | — | — |
| `d3d11va` | `--enable-d3d11va` | Direct3D 11 Video Acceleration | — | — | — |
| `d3d12va` | `--enable-d3d12va` | Direct3D 12 Video Acceleration | — | — | `>=7.0` |
| `dxva2` | `--enable-dxva2` | DXVA2 hardware decoding | — | — | — |
| `mediafoundation` | `--enable-mediafoundation` | Media Foundation support | — | — | `>=4.0` |
| `pthreads` | `--enable-pthreads` | POSIX threads support | — | — | — |

## GPL

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `x264` | `--enable-libx264` | H.264 encoding via x264 | `x264`, `@license-gpl` | — | — |
| `x265` | `--enable-libx265` | HEVC encoding via x265 | `x265`, `@license-gpl` | `!uwp & !xbox` | — |
| `dvdnav` | `--enable-libdvdnav` | DVD, Blu-ray, and Matroska navigation via libdvdnav | `libdvdnav`, `@license-gpl` | `!uwp & !xbox` | `>=7.0` |
| `dvdread` | `--enable-libdvdread` | DVD reading support via libdvdread | `libdvdread`, `@license-gpl` | `!uwp & !xbox` | `>=7.0` |

## Non-free

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `fdk-aac` | `--enable-libfdk-aac` | AAC de/encoding via libfdk-aac | `fdk-aac`, `@license-nonfree` | — | `>=4.0` |

## Meta Features

| Feature | Configure Flag | Description | Dependencies | Platform | Since |
|---------|---------------|-------------|-------------|----------|-------|
| `static` | — | Build FFmpeg as static libraries instead of shared | — | — | — |
| `ffplay` | `--enable-ffplay` | Build the ffplay application | `@base` | — | — |
| `ffmpeg` | `--enable-ffmpeg` | Build the ffmpeg application | `@base` | — | — |
| `ffprobe` | `--enable-ffprobe` | Build the ffprobe application | `@base` | — | — |
| `base` | — | Build all libraries | `@avcodec`, `@avdevice`, `@avformat`, `@avfilter`, `@swresample`, `@swscale` | — | — |
| `app` | — | Build all applications | `@ffmpeg`, `@ffplay`, `@ffprobe` | — | — |
| `windows-hw` | — | Windows hardware acceleration features | `@d3d11va`, `@d3d12va`, `@dxva2`, `@mediafoundation`, `@w32threads` | — | — |
| `all` | — | All LGPL features plus Windows hardware acceleration | `@lgpl`, `@windows-hw` | — | — |
| `lgpl` | — | All LGPL-licensed optional features | `@zlib`, `@bzip2`, `@lzma`, `@iconv`, `@freetype`, `@fribidi`, `@fontconfig`, `@harfbuzz`, `@ass`, `@bluray`, `@opus`, `@vorbis`, `@theora`, `@speex`, `@mp3lame`, `@soxr`, `@openmpt`, `@ilbc`, `@modplug`, `@gme`, `@mysofa`, `@tesseract`, `@dav1d`, `@aom`, `@vpx`, `@webp`, `@openjpeg`, `@snappy`, `@openh264`, `@jxl`, `@lensfun`, `@shaderc`, `@svtav1`, `@vvenc`, `@sdl2`, `@xml2`, `@vulkan`, `@opencl`, `@opengl`, `@srt`, `@ssh`, `@openssl`, `@zmq`, `@nvcodec`, `@amf` | — | — |
| `all-lgpl` | — | Meta-feature: all + lgpl | `@all`, `@lgpl` | — | — |
| `gpl` | — | All GPL-licensed features | `@dvdnav`, `@dvdread`, `@x264`, `@x265`, `@postproc` | — | — |
| `all-gpl` | — | Meta-feature: all + gpl | `@all`, `@gpl` | — | — |
| `nonfree` | — | All non-free features | `@fdk-aac` | — | — |
| `all-nonfree` | — | Meta-feature: all features including non-free | `@all`, `@gpl`, `@lgpl`, `@nonfree` | — | — |

## License Summary

**GPL features** (require `--enable-gpl`): `postproc`, `x264`, `x265`, `dvdnav`, `dvdread`

**Non-free features** (require `--enable-nonfree`): `fdk-aac`

**Platform-restricted features**: `fribidi`, `fontconfig`, `harfbuzz`, `modplug`, `tesseract`, `aom`, `lensfun`, `svtav1`, `vvenc`, `srt`, `ssh`, `zmq`, `bluray`, `nvcodec`, `qsv`, `mfx`, `vulkan`, `opencl`, `opengl`, `x265`, `dvdnav`, `dvdread`