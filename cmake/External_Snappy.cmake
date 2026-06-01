# ---- Registration ----
dep_package(
    NAME        snappy
    DEFAULT     1.2.2
    BUILD       cmake
    FFMPEG_FLAG --enable-libsnappy
)
dep_package_version(NAME snappy VERSION 1.2.2
    URL      "https://github.com/google/snappy/archive/refs/tags/1.2.2.tar.gz"
)

# ---- Build function ----
function(build_snappy)
    ExternalProject_Add(snappy_target
        URL          ${SNAPPY_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/snappy"
        PATCH_COMMAND ${SNAPPY_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DSNAPPY_BUILD_TESTS=OFF
            -DSNAPPY_BUILD_BENCHMARKS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/snappy.lib"
            "${STAGE_DIR}/lib/pkgconfig/snappy.pc"
    )
    add_pkgconfig_file(snappy_target snappy.pc snappy 1.2.2 "A fast compression/decompression library")
endfunction()
