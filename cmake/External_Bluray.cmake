# ---- Registration ----
dep_package(
    NAME        bluray
    DEFAULT     1.4.1
    BUILD       meson
    FFMPEG_FLAG --enable-libbluray
    REQUIRES    libxml2;freetype
)
dep_package_version(NAME bluray VERSION 1.4.1
    URL "https://download.videolan.org/pub/videolan/libbluray/1.4.1/libbluray-1.4.1.tar.xz"
    PATCHES bluray/bluray_deps.patch
)

# ---- Build function ----
function(build_bluray)
    skip_if_staged_target(bluray_target
        LIBS libbluray
    )
    ExternalProject_Add(bluray_target
        DEPENDS      ${BLURAY_RESOLVED_DEPENDS}
        URL          ${BLURAY_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/bluray"
        PATCH_COMMAND ${BLURAY_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
                -Dfreetype=enabled
                -Dlibxml2=enabled
                -Dfontconfig=disabled
                -Dbdj_jar=disabled
                -Djava9=false
                -Dembed_udfread=true
                -Denable_tools=false
                -Denable_devtools=false
                -Denable_examples=false
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/bluray.lib"
            "${STAGE_DIR}/lib/pkgconfig/libbluray.pc"
    )
    add_rename_step(bluray_target libbluray.a bluray.lib)
endfunction()
