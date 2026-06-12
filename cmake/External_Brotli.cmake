# ---- Registration ----
dep_package(
    NAME    brotli
    DEFAULT 1.1.0
    BUILD   cmake
)
dep_package_version(NAME brotli VERSION 1.1.0
    URL "https://github.com/google/brotli/archive/refs/tags/v1.1.0.tar.gz"
)

# ---- Build function ----
function(build_brotli)
    skip_if_staged_target(brotli_target LIBS libbrotlicommon;libbrotlienc;libbrotlidec)
    ExternalProject_Add(brotli_target
        URL          ${BROTLI_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/brotli"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/brotlicommon.lib"
            "${STAGE_DIR}/lib/brotlienc.lib"
            "${STAGE_DIR}/lib/brotlidec.lib"
            "${STAGE_DIR}/lib/pkgconfig/libbrotlicommon.pc"
            "${STAGE_DIR}/lib/pkgconfig/libbrotlienc.pc"
            "${STAGE_DIR}/lib/pkgconfig/libbrotlidec.pc"
    )
endfunction()
