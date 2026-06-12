# ---- Registration ----
dep_package(
    NAME        soxr
    DEFAULT     0.1.3
    BUILD       cmake
    FFMPEG_FLAG --enable-libsoxr
)
dep_package_version(NAME soxr VERSION 0.1.3
    URL "https://downloads.sourceforge.net/project/soxr/soxr-0.1.3-Source.tar.xz"
    PATCHES soxr/enable_pc.patch
)

if(TARGET_ARCH STREQUAL "arm")
    set(SOXR_CMAKE_ARGS 
        -DCMAKE_C_FLAGS="-DPFFFT_SIMD_DISABLE"
        -DCOMPILE_WITH_SIMD=OFF
        -DWITH_CR32S=OFF
        -DWITH_CR64S=OFF
        -DWITH_PFFFT=OFF
        -DBUILD_TESTS=OFF
    )
endif()
# ---- Build function ----
function(build_soxr)
    skip_if_staged_target(soxr_target
        LIBS soxr
    )
    ExternalProject_Add(soxr_target
        URL          ${SOXR_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/soxr"
        PATCH_COMMAND ${SOXR_RESOLVED_PATCH_CMDS}

        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            ${SOXR_CMAKE_ARGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/soxr.lib"
            "${STAGE_DIR}/lib/pkgconfig/soxr.pc"
    )
endfunction()
