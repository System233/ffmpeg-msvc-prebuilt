# ---- Registration ----
dep_package(
    NAME        libxml2
    DEFAULT     2.13.5
    BUILD       cmake
    FFMPEG_FLAG --enable-libxml2
)
dep_package_version(NAME libxml2 VERSION 2.13.5
    URL "https://github.com/GNOME/libxml2/archive/refs/tags/v2.13.5.tar.gz"
)

# ---- Build function ----
function(build_libxml2)
    skip_if_staged_target(libxml2_target
        LIBS libxml-2.0
    )
    ExternalProject_Add(libxml2_target
        URL          ${LIBXML2_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/libxml2"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DLIBXML2_WITH_ICONV=OFF
            -DLIBXML2_WITH_PYTHON=OFF
            -DLIBXML2_WITH_LZMA=OFF
            -DLIBXML2_WITH_ZLIB=OFF
            -DLIBXML2_WITH_PROGRAMS=OFF
            -DLIBXML2_WITH_TESTS=OFF
            -DLIBXML2_WITH_HTTP=OFF
            -DLIBXML2_WITH_FTP=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libxml2.lib"
            "${STAGE_DIR}/lib/pkgconfig/libxml-2.0.pc"
    )
    add_rename_step(libxml2_target libxml2s.lib xml2.lib)
endfunction()
