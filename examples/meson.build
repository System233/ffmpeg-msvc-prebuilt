project('ffmeta', 'c')

# Find FFmpeg via pkg-config
# Set PKG_CONFIG_PATH to <prefix>/lib/pkgconfig before running:
#   PKG_CONFIG_PATH=<prefix>/lib/pkgconfig meson setup build
#
# Or use the --pkg-config-path option:
#   meson setup build -Dpkg_config_path=<prefix>/lib/pkgconfig

avformat_dep = dependency('libavformat', required: true)
avcodec_dep  = dependency('libavcodec',  required: true)
avutil_dep   = dependency('libavutil',   required: true)

executable('ffmeta', 'main.c',
    dependencies: [avformat_dep, avcodec_dep, avutil_dep],
    install: true)
