# ---- Registration ----
dep_package(
    NAME        zlib
    DEFAULT     1.3.1
    BUILD       cmake
    FFMPEG_FLAG --enable-zlib
)
dep_package_version(NAME zlib VERSION 1.3.1
    URL      "https://github.com/madler/zlib/archive/refs/tags/v1.3.1.tar.gz"
    PATCHES  zlib/msvc-shared-libs.patch
)
dep_package_version(NAME zlib VERSION 1.2.13
    URL      "https://github.com/madler/zlib/archive/refs/tags/v1.2.13.tar.gz"
    PATCHES  zlib/msvc-shared-libs.patch
)

# ---- Build function ----
function(build_zlib)
    skip_if_staged_target(zlib_target
        LIBS zlib
    )
    ExternalProject_Add(zlib_target
        URL          ${ZLIB_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/zlib"
        PATCH_COMMAND ${ZLIB_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DZLIB_BUILD_EXAMPLES=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/zlib.lib"
            "${STAGE_DIR}/lib/pkgconfig/zlib.pc"
    )
endfunction()
