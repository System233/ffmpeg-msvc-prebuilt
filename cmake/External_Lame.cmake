# ---- Registration ----
dep_package(
    NAME        mp3lame
    DEFAULT     3.100
    BUILD       autotools
    FFMPEG_FLAG --enable-libmp3lame
)
dep_package_version(NAME mp3lame VERSION 3.100
    URL "https://sourceforge.net/projects/lame/files/lame/3.100/lame-3.100.tar.gz"
)


# ---- Build function ----
function(build_mp3lame)
    ExternalProject_Add(mp3lame_target
        URL          ${MP3LAME_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/mp3lame"
        PATCH_COMMAND ${MP3LAME_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ./configure
                --prefix=${STAGE_DIR}
                --enable-static
                --disable-shared
                --enable-shared=no
                --disable-frontend
                --host=${HOST_TRIPLE}
                --disable-dependency-tracking
                ${MP3LAME_ARCH_FLAGS}
                ${COMPAT_ENV} 
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR> 
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libmp3lame.lib"
            "${STAGE_DIR}/lib/pkgconfig/lame.pc"
    )
    add_libtool_step(mp3lame_target)
    add_rename_step(mp3lame_target libmp3lame.lib mp3lame.lib)
    add_pkgconfig_file(mp3lame_target lame.pc mp3lame 3.100 "LAME MP3 encoder library")

    #     ExternalProject_Add(mp3lame_target
    #     URL          ${MP3LAME_RESOLVED_URL}
    #     DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
    #     SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/mp3lame"
    #     CONFIGURE_COMMAND
    #         meson setup <BINARY_DIR> <SOURCE_DIR>
    #             --prefix=${STAGE_DIR}
    #             --buildtype=release
    #             --default-library=static
    #             --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
    #             -Db_vscrt=mt
    #     BUILD_COMMAND
    #         meson compile -C <BINARY_DIR>
    #     INSTALL_COMMAND
    #         meson install -C <BINARY_DIR>
    #     BUILD_BYPRODUCTS
    #         "${STAGE_DIR}/lib/mp3lame.lib"
    #         "${STAGE_DIR}/lib/pkgconfig/mp3lame.pc"
    # )
    # ExternalProject_Add_Step(mp3lame_target copy_meson_build
    #     COMMAND ${CMAKE_COMMAND} -E copy_if_different
    #         "${CMAKE_CURRENT_LIST_DIR}/../patches/mp3lame/meson.build"
    #         <SOURCE_DIR>/meson.build
    #     DEPENDEES download update patch
    #     DEPENDERS configure
    # )
    # add_rename_step(mp3lame_target libmp3lame.a mp3lame.lib)

endfunction()
