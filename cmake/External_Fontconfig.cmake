# ---- Registration ----
dep_package(
    NAME        fontconfig
    DEFAULT     2.15.0
    BUILD       meson
    FFMPEG_FLAG --enable-libfontconfig
    REQUIRES    freetype;expat
)
dep_package_version(NAME fontconfig VERSION 2.15.0
    URL "https://gitlab.freedesktop.org/fontconfig/fontconfig/-/archive/2.15.0/fontconfig-2.15.0.tar.gz"
)

# ---- Build function ----
function(build_fontconfig)
    skip_if_staged_target(fontconfig_target
        LIBS fontconfig
    )
    ExternalProject_Add(fontconfig_target
        DEPENDS      ${FONTCONFIG_RESOLVED_DEPENDS}
        URL          ${FONTCONFIG_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/fontconfig"
        CONFIGURE_COMMAND
            meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
                -Dnls=disabled
                -Dcache-build=disabled
                -Dtests=disabled
                -Dtools=disabled
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libfontconfig.lib"
            "${STAGE_DIR}/lib/pkgconfig/fontconfig.pc"
    )
    add_rename_step(fontconfig_target libfontconfig.a libfontconfig.lib)
endfunction()
