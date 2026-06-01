# FFmpeg 7.x family — covers >=7.0 <8.0
ffmpeg_family(
    NAME            7.x
    VERSION_RANGE   ">=7.0 <8.0"
    URL_TEMPLATE    "https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n${FFMPEG_VERSION}.tar.gz"
    PATCHES         ffmpeg/textutils-time-internal.patch
    CONFIGURE_FLAGS --enable-version3  
    DEPS
        zlib>=1.2.0
        x264
        fribidi>=1.0.0
        freetype
        harfbuzz
        libass>=0.17.0
        libjxl
        x265
        libvpx
        dav1d
        opus
        soxr
        sdl2
        libwebp
        nvcodec
        srt
        libxml2
        svtav1
        aom
        mp3lame
        openjpeg
        snappy
        vvenc
        liblc3
        # pthreads
#        codec2
        # vmaf
        gsm
#        speex
        twolame
        bs2b
        gme
)
