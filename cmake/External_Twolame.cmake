# ---- Registration ----
dep_package(
    NAME        twolame
    DEFAULT     0.4.0
    BUILD       meson
    FFMPEG_FLAG --enable-libtwolame
    LICENSE     lgpl
)
dep_package_version(NAME twolame VERSION 0.4.0
    URL      "https://sourceforge.net/projects/twolame/files/twolame/0.4.0/twolame-0.4.0.tar.gz"
    PATCHES  twolame/msvc-static-lib.patch
)

# ---- Build function ----
function(build_twolame)
    skip_if_staged_target(twolame_target
        LIBS twolame
    )
    ExternalProject_Add(twolame_target
        URL          ${TWOLAME_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/twolame"
        PATCH_COMMAND ${TWOLAME_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/twolame.lib"
            "${STAGE_DIR}/lib/pkgconfig/twolame.pc"
    )
    ExternalProject_Add_Step(twolame_target copy_meson_build
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_LIST_DIR}/../patches/twolame/meson.build"
            <SOURCE_DIR>/meson.build
        DEPENDEES download update patch
        DEPENDERS configure
    )
    add_rename_step(twolame_target libtwolame.a twolame.lib)
endfunction()
