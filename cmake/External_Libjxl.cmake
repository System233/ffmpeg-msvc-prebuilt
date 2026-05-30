# ---- Registration ----
dep_package(
    NAME        libjxl
    DEFAULT     0.11.1
    BUILD       cmake
    FFMPEG_FLAG --enable-libjxl
    REQUIRES    highway;brotli;lcms2
)
dep_package_version(NAME libjxl VERSION 0.11.1
    URL      "https://github.com/libjxl/libjxl/archive/refs/tags/v0.11.1.tar.gz"
    PATCHES  libjxl/msvc-pkgconfig-no-lm.patch
)

# ---- Build function ----
function(build_libjxl)
    ExternalProject_Add(libjxl_target
        DEPENDS      ${LIBJXL_RESOLVED_DEPENDS}
        URL          ${LIBJXL_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/libjxl"
        PATCH_COMMAND ${LIBJXL_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_PREFIX_PATH=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
            -DBUILD_TESTING=OFF
            -DJPEGXL_ENABLE_TOOLS=OFF
            -DJPEGXL_ENABLE_EXAMPLES=OFF
            -DJPEGXL_ENABLE_BENCHMARK=OFF
            -DJPEGXL_ENABLE_JNI=OFF
            -DJPEGXL_BUNDLE_LIBPNG=OFF
            -DJPEGXL_ENABLE_OPENEXR=OFF
            -DJPEGXL_ENABLE_SJPEG=OFF
            -DJPEGXL_ENABLE_DOXYGEN=OFF
            -DJPEGXL_ENABLE_MANPAGES=OFF
            -DJPEGXL_ENABLE_SKCMS=OFF
            -DJPEGXL_FORCE_SYSTEM_LCMS2=ON
            -DJPEGXL_STATIC=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/jxl.lib"
            "${STAGE_DIR}/lib/pkgconfig/libjxl.pc"
    )
endfunction()
