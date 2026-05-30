# FFmpeg 6.x family — covers >=6.0 <7.0
ffmpeg_family(
    NAME            6.x
    VERSION_RANGE   ">=6.0 <7.0"
    URL_TEMPLATE    "https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n${FFMPEG_VERSION}.tar.gz"
    CONFIGURE_FLAGS --enable-version3
    DEPS
        zlib
        x264
        fribidi
        freetype
        harfbuzz
        libass
        openexr
        libjxl
        x265
        libvpx
        dav1d
        opus
        soxr
        sdl2
        libwebp
        nvcodec
)
