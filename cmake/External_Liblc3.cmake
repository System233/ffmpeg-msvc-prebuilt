# ---- Registration ----
dep_package(
    NAME        liblc3
    DEFAULT     1.1.3
    BUILD       meson
    FFMPEG_FLAG --enable-liblc3
    LICENSE     Apache-2.0
)
dep_package_version(NAME liblc3 VERSION 1.1.3
    URL "https://github.com/google/liblc3/archive/refs/tags/v1.1.3.tar.gz"
)

# ---- Build function ----
function(build_liblc3)
    ExternalProject_Add(liblc3_target
        URL          ${LIBLC3_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/liblc3"
        CONFIGURE_COMMAND
            ${SHELL_ENV} meson setup <BINARY_DIR> <SOURCE_DIR>
                -Dc_args="${CMAKE_C_FLAGS}"
                --prefix=${STAGE_DIR}
                --buildtype=release
                --default-library=static
                --vsenv
                -Db_vscrt=mt
                -Dtools=false
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/lc3.lib"
            "${STAGE_DIR}/lib/pkgconfig/lc3.pc"
    )

    add_rename_step(liblc3_target liblc3.a lc3.lib)
endfunction()
