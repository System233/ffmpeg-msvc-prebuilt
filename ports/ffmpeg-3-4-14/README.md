# FFmpeg 3.4.14 — MSVC Prebuilt

Built via [vcpkg](https://github.com/microsoft/vcpkg) 
with MSVC on Windows.

## Usage

```cmake
find_package(FFMPEG REQUIRED)
target_link_libraries(main PRIVATE FFMPEG::ffmpeg)
```

## Features (53 total)

| Feature | Flag | Description | Platform |
|---------|------|-------------|----------|
| ass | `--enable-libass` | Libass subtitles rendering, needed for subtitles and ass filter support in ffmpeg |  |
| avcodec | `--enable-avcodec` | Build the avcodec library |  |
| avdevice | `--enable-avdevice` | Build the avdevice library |  |
| avfilter | `--enable-avfilter` | Build the avfilter library |  |
| avformat | `--enable-avformat` | Build the avformat library |  |
| avresample | `--enable-avresample` | Build the avresample library |  |
| bluray | `--enable-libbluray` | Blu-ray disc support via libbluray | !uwp & !xbox |
| bzip2 | `--enable-bzlib` | Bzip2 support |  |
| d3d11va | `--enable-d3d11va` | Direct3D 11 Video Acceleration |  |
| dxva2 | `--enable-dxva2` | DXVA2 hardware decoding |  |
| fdk-aac | `--enable-libfdk-aac` | AAC de/encoding via libfdk-aac |  |
| fontconfig | `--enable-libfontconfig` | Useful for drawtext filter | !uwp |
| freetype | `--enable-libfreetype` | Needed for drawtext filter |  |
| fribidi | `--enable-libfribidi` | Improves drawtext filter | !uwp |
| gme | `--enable-libgme` | Video game music file de/encoding via libgme |  |
| iconv | `--enable-iconv` | Iconv support |  |
| ilbc | `--enable-libilbc` | iLBC de/encoding via libilbc |  |
| license-gpl | `--enable-gpl --enable-version3` | Allow use of GPL code, the resulting libs and binaries will be under GPL |  |
| license-nonfree | `--enable-nonfree` | Allow use of nonfree code, the resulting libs and binaries will be unredistributable |  |
| lzma | `--enable-lzma` | lzma support |  |
| mfx | `--enable-libmfx` | Intel QSV Codec via libmfx (pre-8.0) | !uwp & !arm & !arm64 |
| modplug | `--enable-libmodplug` | ModPlug via libmodplug | !uwp |
| mp3lame | `--enable-libmp3lame` | MP3 encoding via libmp3lame |  |
| mysofa | `--enable-libmysofa` | Spatial audio via libmysofa |  |
| nvcodec | `--enable-cuda --enable-nvenc` | Nvidia video decoding/encoding acceleration | !uwp & !arm & !arm64 |
| opencl | `--enable-opencl` | OpenCL processing | !uwp |
| opengl | `--enable-opengl` | OpenGL rendering | !uwp & !xbox |
| openh264 | `--enable-libopenh264` | H.264 de/encoding via openh264 |  |
| openjpeg | `--enable-libopenjpeg` | JPEG 2000 de/encoding via OpenJPEG |  |
| openmpt | `--enable-libopenmpt` | Decoding tracked files via libopenmpt |  |
| openssl | `--enable-openssl` | Use OpenSSL for TLS support |  |
| opus | `--enable-libopus` | Opus de/encoding via libopus |  |
| postproc | `--enable-postproc` | Build the postproc library |  |
| pthreads | `--enable-pthreads` | POSIX threads support |  |
| sdl2 | `--enable-sdl2` | Sdl2 support |  |
| snappy | `--enable-libsnappy` | Snappy compression, needed for hap encoding |  |
| soxr | `--enable-libsoxr` | Include libsoxr resampling |  |
| speex | `--enable-libspeex` | Speex de/encoding via libspeex |  |
| ssh | `--enable-libssh` | SFTP protocol via libssh | !uwp & !xbox |
| static | `` | Build FFmpeg as static libraries instead of shared |  |
| swresample | `--enable-swresample` | Build the swresample library |  |
| swscale | `--enable-swscale` | Build the swscale library |  |
| tesseract | `--enable-libtesseract` | Optical character recognition via tesseract | !uwp |
| theora | `--enable-libtheora` | Theora encoding via libtheora |  |
| vorbis | `--enable-libvorbis` | Vorbis en/decoding via libvorbis, native implementation exists |  |
| vpx | `--enable-libvpx` | VP8 and VP9 de/encoding via libvpx |  |
| w32threads | `--enable-w32threads` | Windows thread support |  |
| webp | `--enable-libwebp` | WebP encoding via libwebp |  |
| x264 | `--enable-libx264` | H.264 encoding via x264 |  |
| x265 | `--enable-libx265` | HEVC encoding via x265 | !uwp & !xbox |
| xml2 | `--enable-libxml2` | XML parsing using the C library libxml2, needed for dash demuxing support |  |
| zlib | `--enable-zlib` | zlib support |  |
| zmq | `--enable-libzmq` | Enable ZeroMQ support | !uwp & !xbox |

## Meta-Features

| Name | Includes |
|------|----------|
| all | @all-lgpl |
| all-gpl | @all, @gpl, postproc |
| all-lgpl | @lgpl, @windows-hw |
| all-nonfree | @all-gpl, @nonfree |
| gpl | @all-lgpl, dvdnav, dvdread, x264, x265 |
| lgpl | zlib, bzip2, lzma, iconv, freetype, fribidi, fontconfig, harfbuzz, ass, bluray, opus, vorbis, theora, speex, mp3lame, soxr, openmpt, ilbc, modplug, gme, mysofa, tesseract, dav1d, aom, vpx, webp, openjpeg, snappy, openh264, jxl, lensfun, shaderc, svtav1, vvenc, sdl2, xml2, vulkan, opencl, opengl, srt, ssh, openssl, zmq, nvcodec, amf |
| nonfree | fdk-aac |
| windows-hw | d3d11va, d3d12va, dxva2, mediafoundation, w32threads |

## Default Features

avcodec, avdevice, avfilter, avformat, swresample, swscale

## External Dependencies

bzip2, fdk-aac, ffnvcodec, fontconfig, freetype, fribidi, libass, libbluray, libgme, libiconv, libilbc, liblzma, libmodplug, libmysofa, libopenmpt, libssh, libtheora, libvorbis, libvpx, libwebp, libxml2, mfx-dispatch, mp3lame, opencl, opengl, openh264, openjpeg, openssl, opus, sdl2, snappy, soxr, speex, tesseract, x264, x265, zeromq, zlib
