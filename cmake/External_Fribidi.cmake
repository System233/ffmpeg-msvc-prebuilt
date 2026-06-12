# ---- Registration ----
dep_package(
    NAME        fribidi
    DEFAULT     1.0.16
    BUILD       meson
    FFMPEG_FLAG --enable-libfribidi
)
dep_package_version(NAME fribidi VERSION 1.0.16
    URL      "https://github.com/fribidi/fribidi/releases/download/v1.0.16/fribidi-1.0.16.tar.xz"
    PATCHES  fribidi/meson-pregen-tabs.patch
)

# ---- Build function ----
function(build_fribidi)
    skip_if_staged_target(fribidi_target
        LIBS fribidi
    )
    ExternalProject_Add(fribidi_target
        URL          ${FRIBIDI_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/fribidi"
        PATCH_COMMAND ${FRIBIDI_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
                -Ddeprecated=false
                -Ddocs=false
                -Dtests=false
                -Dbin=false
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/fribidi.lib"
            "${STAGE_DIR}/lib/pkgconfig/fribidi.pc"
    )
    add_rename_step(fribidi_target libfribidi.a fribidi.lib)
endfunction()
