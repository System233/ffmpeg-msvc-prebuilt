# ---- Registration ----
dep_package(
    NAME        soxr
    DEFAULT     0.1.3
    BUILD       cmake
    FFMPEG_FLAG --enable-libsoxr
)
dep_package_version(NAME soxr VERSION 0.1.3
    URL "https://downloads.sourceforge.net/project/soxr/soxr-0.1.3-Source.tar.xz"
)

# ---- Build function ----
function(build_soxr)
    ExternalProject_Add(soxr_target
        URL          ${SOXR_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/soxr"
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/soxr.lib"
            "${STAGE_DIR}/lib/pkgconfig/soxr.pc"
    )
endfunction()
