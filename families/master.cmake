# FFmpeg master branch — git clone
ffmpeg_family(
    NAME            master
    VERSION_MATCH   "^master$"
    URL             "https://github.com/FFmpeg/FFmpeg.git"
    URL_TYPE        git
    CONFIGURE_FLAGS --enable-version3 --enable-pthreads --enable-w32threads
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
        srt
        libxml2
        svtav1
        aom
        mp3lame
        vmaf
        openjpeg
        snappy
        vvenc
        liblc3
#        codec2
        gsm
#        speex
        twolame
        bs2b
        gme
        ogg
        vorbis
        theora
        expat
        fontconfig
        bluray
        ssh
        openh264
        ilbc
)
