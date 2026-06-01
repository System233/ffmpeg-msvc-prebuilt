project('twolame', 'c', version: '0.4.0', default_options: ['default_library=static'])

twolame_sources = [
    'libtwolame/ath.c',
    'libtwolame/availbits.c',
    'libtwolame/bitbuffer.c',
    'libtwolame/crc.c',
    'libtwolame/dab.c',
    'libtwolame/encode.c',
    'libtwolame/energy.c',
    'libtwolame/fft.c',
    'libtwolame/get_set.c',
    'libtwolame/mem.c',
    'libtwolame/psycho_0.c',
    'libtwolame/psycho_1.c',
    'libtwolame/psycho_2.c',
    'libtwolame/psycho_3.c',
    'libtwolame/psycho_4.c',
    'libtwolame/psycho_n1.c',
    'libtwolame/subband.c',
    'libtwolame/twolame.c',
    'libtwolame/util.c',
]

twolame_inc = include_directories('libtwolame')

twolame_lib = static_library('twolame', twolame_sources,
    include_directories: twolame_inc,
    install: true,
)

install_headers('libtwolame/twolame.h')

pkg = import('pkgconfig')
pkg.generate(twolame_lib,
    name: 'twolame',
    description: 'MPEG Audio Layer 2 encoder',
)
