project('bs2b', 'c', 'cpp', version: '3.1.0', default_options: ['default_library=static'])

cc = meson.get_compiler('c')
m_dep = cc.find_library('m', required: false)

bs2b_sources = [
    'src/bs2b.c',
    'src/bs2bclass.cpp',
]

bs2b_inc = include_directories('src')

bs2b_lib = static_library('bs2b', bs2b_sources,
    include_directories: bs2b_inc,
    dependencies: m_dep,
    install: true,
)

bs2b_headers = [
    'src/bs2b.h',
    'src/bs2bclass.h',
    'src/bs2btypes.h',
    'src/bs2bversion.h',
]
install_headers(bs2b_headers, subdir: 'bs2b')

pkg = import('pkgconfig')
pkg.generate(bs2b_lib,
    name: 'libbs2b',
    description: 'Bauer stereophonic-to-binaural DSP library',
    subdirs: 'bs2b',
)