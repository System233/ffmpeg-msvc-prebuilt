# ---- Link type handling (shared/static only applies to FFmpeg) ----
if(LINK_TYPE STREQUAL "shared")
    set(FFMPEG_LINK_ARG "--enable-shared")
    set(FFMPEG_BUILD_BYPRODUCTS
        "${STAGE_DIR}/bin/ffmpeg.exe"
        "${STAGE_DIR}/bin/avcodec-61.dll"
        "${STAGE_DIR}/bin/avformat-61.dll"
        "${STAGE_DIR}/lib/avcodec.lib"
        "${STAGE_DIR}/lib/pkgconfig/libavcodec.pc"
    )
else()
    set(FFMPEG_LINK_ARG "--disable-shared")
    set(FFMPEG_BUILD_BYPRODUCTS
        "${STAGE_DIR}/bin/ffmpeg.exe"
        "${STAGE_DIR}/lib/avcodec.lib"
        "${STAGE_DIR}/lib/pkgconfig/libavcodec.pc"
    )
endif()

# ---- License: enable GPL if applicable ----
if(LICENSE STREQUAL "gpl")
    set(FFMPEG_GPL_FLAG "--enable-gpl")
else()
    set(FFMPEG_GPL_FLAG "")
endif()

# ---- Architecture-specific flags ----
if(TARGET_ARCH MATCHES "^arm")
    set(FFMPEG_ARCH_FLAGS "--enable-cross-compile")
else()
    set(FFMPEG_ARCH_FLAGS "")
endif()

# ---- Build function ----
function(build_ffmpeg)
    ExternalProject_Add(ffmpeg_target
        DEPENDS      ${FFMPEG_ASM_DEPENDS}
        URL          ${FFMPEG_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/ffmpeg"
        PATCH_COMMAND ${FFMPEG_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ${SHELL_ENV}
            "LDFLAGS=-libpath:${STAGE_DIR}/lib"
            "CFLAGS=$ENV{CFLAGS} -I${STAGE_DIR}/include"
            ./configure
                --toolchain=msvc
                --arch=${ARCH_NAME}
                --prefix=${STAGE_DIR}
                --pkg-config-flags=-static
                ${FFMPEG_LINK_ARG}
                ${FFMPEG_ASM_FLAGS}
                ${FFMPEG_GPL_FLAG}
                ${FFMPEG_ARCH_FLAGS}
                --enable-version3
                "--as=${CMAKE_CURRENT_LIST_DIR}/compile-as"
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install prefix=${STAGE_DIR}
        BUILD_BYPRODUCTS
            ${FFMPEG_BUILD_BYPRODUCTS}
        BUILD_IN_SOURCE 1
    )
    
    # ExternalProject_Add_Step(ffmpeg_target patch_pkg_config
    #     COMMAND ${CMAKE_COMMAND} 
    #         -DSTAGE_DIR=${STAGE_DIR}
    #         -DSTAGE_DIR3=${STAGE_DIR}
    #         -P ${CMAKE_CURRENT_LIST_DIR}/PatchPkgConfig.cmake
    #     DEPENDEES install
    #     COMMENT "Patching pkg-config files for relocatable paths"
    # )
endfunction()
