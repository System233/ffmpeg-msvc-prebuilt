project('mp3lame', 'c', version: '3.100', default_options: ['default_library=static'])

cc = meson.get_compiler('c')
nasm = find_program('nasm', required: false)

# ---- Config header ----
cdata = configuration_data()
cdata.set('PACKAGE', '"lame"')
cdata.set('VERSION', '"3.100"')
cdata.set('PROTOTYPES', 1)
cdata.set('LAME_LIBRARY_BUILD', 1)
cdata.set('STDC_HEADERS', 1)
cdata.set('USE_FAST_LOG', 1)

cdata.set('SIZEOF_DOUBLE', cc.sizeof('double'))
cdata.set('SIZEOF_FLOAT', cc.sizeof('float'))
cdata.set('SIZEOF_INT', cc.sizeof('int'))
cdata.set('SIZEOF_LONG', cc.sizeof('long'))
cdata.set('SIZEOF_LONG_DOUBLE', cc.sizeof('long double'))
cdata.set('SIZEOF_SHORT', cc.sizeof('short'))

foreach h : ['errno.h', 'fcntl.h', 'limits.h']
    cdata.set('HAVE_' + h.underscorify().to_upper(), 1)
endforeach

cdata.set10('HAVE_STRCHR', cc.has_function('strchr'))
cdata.set10('HAVE_MEMCPY', cc.has_function('memcpy'))

if nasm.found() and cc.has_header('xmmintrin.h')
    cdata.set('HAVE_NASM', 1)
    cdata.set('HAVE_XMMINTRIN_H', 1)
endif

config_h = configure_file(output: 'config.h', configuration: cdata)

mp3lame_sources = [
    'libmp3lame/VbrTag.c',
    'libmp3lame/bitstream.c',
    'libmp3lame/encoder.c',
    'libmp3lame/fft.c',
    'libmp3lame/gain_analysis.c',
    'libmp3lame/id3tag.c',
    'libmp3lame/lame.c',
    'libmp3lame/mpglib_interface.c',
    'libmp3lame/newmdct.c',
    'libmp3lame/presets.c',
    'libmp3lame/psymodel.c',
    'libmp3lame/quantize.c',
    'libmp3lame/quantize_pvt.c',
    'libmp3lame/reservoir.c',
    'libmp3lame/set_get.c',
    'libmp3lame/tables.c',
    'libmp3lame/takehiro.c',
    'libmp3lame/util.c',
    'libmp3lame/vbrquantize.c',
    'libmp3lame/version.c',
]

mp3lame_c_args = []
if cc.has_header('xmmintrin.h')
    mp3lame_sources += 'libmp3lame/vector/xmm_quantize_sub.c'
    mp3lame_c_args += '-DHAVE_XMMINTRIN_H'
endif

mp3lame_inc = include_directories('include', 'libmp3lame')

mp3lame_lib = static_library('mp3lame', mp3lame_sources, config_h,
    include_directories: mp3lame_inc,
    c_args: ['-DHAVE_CONFIG_H'] + mp3lame_c_args,
    install: true,
)

install_headers('include/lame.h', subdir: 'lame')

pkg = import('pkgconfig')
pkg.generate(mp3lame_lib,
    name: 'mp3lame',
    description: 'LAME MP3 encoder library',
    subdirs: 'lame',
)
