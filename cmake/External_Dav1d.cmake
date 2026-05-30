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
    ExternalProject_Add(dav1d_target
        URL          ${DAV1D_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/dav1d"
        CONFIGURE_COMMAND
            ${SHELL_ENV} meson setup <BINARY_DIR> <SOURCE_DIR>
                -Dc_args="${CMAKE_C_FLAGS}"
                -Dcpp_args="${CMAKE_CXX_FLAGS}"
                --prefix=${STAGE_DIR}
                --buildtype=release
                --default-library=static
                --vsenv
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/dav1d.lib"
            "${STAGE_DIR}/lib/pkgconfig/dav1d.pc"
    )
    
    ExternalProject_Add_Step(dav1d_target rename
        COMMAND ${CMAKE_COMMAND} -E 
            rename 
            ${STAGE_DIR}/lib/libdav1d.a 
            ${STAGE_DIR}/lib/dav1d.lib
        DEPENDEES install
    )
endfunction()
