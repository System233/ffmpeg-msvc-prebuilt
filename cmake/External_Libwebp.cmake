# ---- Registration ----
dep_package(
    NAME        libwebp
    DEFAULT     1.5.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libwebp
)
dep_package_version(NAME libwebp VERSION 1.5.0
    URL "https://github.com/webmproject/libwebp/archive/refs/tags/v1.5.0.tar.gz"
)

# ---- Build function ----
function(build_libwebp)
    ExternalProject_Add(libwebp_target
        URL          ${LIBWEBP_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/libwebp"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DWEBP_BUILD_ANIM_UTILS=OFF
            -DWEBP_BUILD_CWEBP=OFF
            -DWEBP_BUILD_DWEBP=OFF
            -DWEBP_BUILD_GIF2WEBP=OFF
            -DWEBP_BUILD_IMG2WEBP=OFF
            -DWEBP_BUILD_VWEBP=OFF
            -DWEBP_BUILD_WEBPINFO=OFF
            -DWEBP_BUILD_WEBPMUX=OFF
            -DWEBP_BUILD_EXTRAS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/webp.lib"
            "${STAGE_DIR}/lib/pkgconfig/libwebp.pc"
    )
endfunction()
