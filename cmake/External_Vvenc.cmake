# ---- Registration ----
dep_package(
    NAME        vvenc
    DEFAULT     1.14.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libvvenc
)
dep_package_version(NAME vvenc VERSION 1.14.0
    URL "https://github.com/fraunhoferhhi/vvenc/archive/refs/tags/v1.14.0.tar.gz"
)

# ---- Build function ----
function(build_vvenc)
    ExternalProject_Add(vvenc_target
        URL          ${VVENC_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/vvenc"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DVVENC_LIBRARY_ONLY=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/vvenc.lib"
            "${STAGE_DIR}/lib/pkgconfig/libvvenc.pc"
    )
endfunction()
