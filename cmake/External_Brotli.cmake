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
    ExternalProject_Add(brotli_target
        URL          ${BROTLI_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/brotli"
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/brotlicommon.lib"
            "${STAGE_DIR}/lib/pkgconfig/libbrotlicommon.pc"
    )
endfunction()
