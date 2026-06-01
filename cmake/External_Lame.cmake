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

# ---- Architecture-specific flags ----
if(TARGET_ARCH MATCHES "^arm")
    set(MP3LAME_ARCH_FLAGS "--disable-asm")
else()
    set(MP3LAME_ARCH_FLAGS "")
endif()

# ---- Build function ----
function(build_mp3lame)
    ExternalProject_Add(mp3lame_target
        URL          ${MP3LAME_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/mp3lame"
        PATCH_COMMAND ${MP3LAME_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ${SHELL_COMPAT_ENV} 
            ./configure
                --prefix=${STAGE_DIR}
                --enable-static
                --disable-shared
                --disable-frontend
                --host=${HOST_TRIPLE}
                --disable-dependency-tracking
                ${MP3LAME_ARCH_FLAGS}
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libmp3lame.lib"
            "${STAGE_DIR}/lib/pkgconfig/lame.pc"
    )
    add_pkgconfig_file(mp3lame_target lame.pc mp3lame 3.100 "LAME MP3 encoder library")
endfunction()
