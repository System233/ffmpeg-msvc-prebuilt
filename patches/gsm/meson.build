project('gsm', 'c', version: '1.0.24', default_options: ['default_library=static'])

gsm_sources = [
    'src/add.c',
    'src/code.c',
    'src/debug.c',
    'src/decode.c',
    'src/long_term.c',
    'src/lpc.c',
    'src/preprocess.c',
    'src/rpe.c',
    'src/gsm_destroy.c',
    'src/gsm_decode.c',
    'src/gsm_encode.c',
    'src/gsm_explode.c',
    'src/gsm_implode.c',
    'src/gsm_create.c',
    'src/gsm_print.c',
    'src/gsm_option.c',
    'src/short_term.c',
    'src/table.c',
]

gsm_inc = include_directories('inc')

gsm_lib = static_library('gsm', gsm_sources,
    include_directories: gsm_inc,
    c_args: ['-DSASR', '-DWAV49', '-DNeedFunctionPrototypes=1'],
    install: true,
)

install_headers('inc/gsm.h', subdir: 'gsm')

pkg = import('pkgconfig')
pkg.generate(gsm_lib,
    name: 'gsm',
    description: 'GSM 06.10 codec library',
    subdirs: 'gsm',
)
