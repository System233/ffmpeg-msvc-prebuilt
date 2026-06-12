# ---- Registration ----
dep_package(
    NAME        svtav1
    DEFAULT     2.3.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libsvtav1
)
dep_package_version(NAME svtav1 VERSION 2.3.0
    URL "https://gitlab.com/AOMediaCodec/SVT-AV1/-/archive/v2.3.0/SVT-AV1-v2.3.0.tar.gz"
)
if(TARGET_ARCH STREQUAL "arm64")
    set(SVTAV1_BUILD_FLAGS 
            -DCOMPILE_C_ONLY=ON
    )
endif()
# ---- Build function ----
function(build_svtav1)
    skip_if_staged_target(svtav1_target
        LIBS SvtAv1Enc
    )
    ExternalProject_Add(svtav1_target
        URL          ${SVTAV1_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/svtav1"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DBUILD_APPS=OFF
            -DBUILD_TESTING=OFF
            -DBUILD_DEC=OFF
            -DREPRODUCIBLE_BUILDS=ON
            -DSVT_AV1_LTO=OFF
            ${SVTAV1_BUILD_FLAGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/SvtAv1Enc.lib"
            "${STAGE_DIR}/lib/pkgconfig/SvtAv1Enc.pc"
    )
endfunction()
