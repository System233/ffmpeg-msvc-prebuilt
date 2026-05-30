# FFmpeg 4.x family — covers >=4.0 <5.0
ffmpeg_family(
    NAME            4.x
    VERSION_RANGE   ">=4.0 <5.0"
    URL_TEMPLATE    "https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n${FFMPEG_VERSION}.tar.gz"
    DEPS
        zlib
        x264
        fribidi
        freetype
        opus
        soxr
)
