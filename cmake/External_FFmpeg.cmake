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

ExternalProject_Add(ffmpeg_target
    DEPENDS        zlib_target x264_target #libass_target
    URL            https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n7.1.4.tar.gz
    DOWNLOAD_DIR   "${CMAKE_CURRENT_BINARY_DIR}/downloads"
    SOURCE_DIR     "${CMAKE_CURRENT_BINARY_DIR}/src/ffmpeg"

    # PATCH_COMMAND
    #     patch -p1 -d <SOURCE_DIR> -i "${CMAKE_CURRENT_LIST_DIR}/../patches/ffmpeg/textutils-time-internal.patch"

    CONFIGURE_COMMAND
        ${SHELL_ENV}

        ./configure
            --toolchain=msvc
            --arch=${ARCH_NAME}
            --prefix=${STAGE_DIR}
            ${FFMPEG_LINK_ARG}
            --enable-zlib
            --enable-libx264
            # --enable-libass
            --enable-gpl
            --enable-version3

    BUILD_COMMAND
        $(MAKE)

    INSTALL_COMMAND
        $(MAKE) install prefix=${STAGE_DIR}

    BUILD_BYPRODUCTS
        ${FFMPEG_BUILD_BYPRODUCTS}

    BUILD_IN_SOURCE 1
)
