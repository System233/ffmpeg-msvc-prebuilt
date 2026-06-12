# ---- Registration ----
dep_package(
    NAME        openh264
    DEFAULT     2.6.0
    BUILD       meson
    FFMPEG_FLAG --enable-libopenh264
)
dep_package_version(NAME openh264 VERSION 2.6.0
    URL "https://github.com/cisco/openh264/archive/refs/tags/v2.6.0.tar.gz"
)

# ---- Build function ----
function(build_openh264)
    skip_if_staged_target(openh264_target
        LIBS openh264
    )
    ExternalProject_Add(openh264_target
        URL          ${OPENH264_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/openh264"
        CONFIGURE_COMMAND
            meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
                -Dtests=disabled
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/openh264.lib"
            "${STAGE_DIR}/lib/pkgconfig/openh264.pc"
    )
    add_rename_step(openh264_target libopenh264.a openh264.lib)
endfunction()
