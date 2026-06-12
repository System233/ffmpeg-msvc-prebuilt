# ---- Registration ----
dep_package(
    NAME        dav1d
    DEFAULT     1.5.1
    BUILD       meson
    FFMPEG_FLAG --enable-libdav1d
)
dep_package_version(NAME dav1d VERSION 1.5.1
    URL "https://github.com/videolan/dav1d/archive/refs/tags/1.5.1.tar.gz"
)

# ---- Build function ----
function(build_dav1d)
    skip_if_staged_target(dav1d_target
        LIBS dav1d
    )
    ExternalProject_Add(dav1d_target
        URL          ${DAV1D_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/dav1d"
        CONFIGURE_COMMAND
            ${SHELL_ENV} meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/dav1d.lib"
            "${STAGE_DIR}/lib/pkgconfig/dav1d.pc"
    )
    
    add_rename_step(dav1d_target libdav1d.a dav1d.lib)
endfunction()
