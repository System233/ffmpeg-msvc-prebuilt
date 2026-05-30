# FFmpeg master branch — git clone
ffmpeg_family(
    NAME            master
    VERSION_MATCH   "^master$"
    URL             "https://github.com/FFmpeg/FFmpeg.git"
    URL_TYPE        git
    CONFIGURE_FLAGS --enable-version3
    DEPS
        zlib
        x264
        fribidi
        freetype
        harfbuzz
        libass
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
