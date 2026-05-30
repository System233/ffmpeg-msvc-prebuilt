# ---- Registration ----
dep_package(
    NAME        dav1d
    DEFAULT     1.5.1
    BUILD       cmake
    FFMPEG_FLAG --enable-libdav1d
)
dep_package_version(NAME dav1d VERSION 1.5.1
    URL "https://github.com/videolan/dav1d/archive/refs/tags/1.5.1.tar.gz"
)

# ---- Build function ----
function(build_dav1d)
    ExternalProject_Add(dav1d_target
        URL          ${DAV1D_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/dav1d"
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/dav1d.lib"
            "${STAGE_DIR}/lib/pkgconfig/dav1d.pc"
    )
endfunction()
