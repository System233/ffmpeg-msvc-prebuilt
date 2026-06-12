# ---- Registration ----
dep_package(
    NAME        vvenc
    DEFAULT     1.14.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libvvenc
)
dep_package_version(NAME vvenc VERSION 1.14.0
    URL "https://github.com/fraunhoferhhi/vvenc/archive/refs/tags/v1.14.0.tar.gz"
    PATCHES vvenc/InterpolationFilter_neon.patch
)
if(TARGET_ARCH STREQUAL "arm")
    set(VVENC_BUILD_FLAGS "-DVVENC_ENABLE_X86_SIMD=OFF")
endif()
# ---- Build function ----
function(build_vvenc)
    skip_if_staged_target(vvenc_target
        LIBS libvvenc
    )
    ExternalProject_Add(vvenc_target
        URL          ${VVENC_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/vvenc"
        PATCH_COMMAND ${VVENC_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            ${VVENC_BUILD_FLAGS}
            -DVVENC_LIBRARY_ONLY=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/vvenc.lib"
            "${STAGE_DIR}/lib/pkgconfig/libvvenc.pc"
    )
endfunction()
