project('bs2b', 'c', version: '3.1.0', default_options: ['default_library=static'])

bs2b_sources = [
    'src/bs2b.c',
    'src/bs2bconvert.c',
    'src/bs2bstream.c',
]

bs2b_inc = include_directories('src')

sndfile_dep = dependency('sndfile', required: true)

bs2b_lib = static_library('bs2b', bs2b_sources,
    include_directories: bs2b_inc,
    dependencies: sndfile_dep,
    install: true,
)

install_headers('src/bs2b.h', subdir: 'bs2b')

pkg = import('pkgconfig')
pkg.generate(bs2b_lib,
    name: 'bs2b',
    description: 'Bauer stereophonic-to-binaural DSP library',
    subdirs: 'bs2b',
)
