# ---- Registration ----
dep_package(
    NAME        libvpx
    DEFAULT     1.15.0
    BUILD       autotools
    FFMPEG_FLAG --enable-libvpx
)
dep_package_version(NAME libvpx VERSION 1.15.0
    URL      "https://github.com/webmproject/libvpx/archive/refs/tags/v1.15.0.tar.gz"
    # PATCHES  libvpx/msvc-configure-checks.patch;libvpx/msvc-build-fixes.patch
)

# ---- Build function ----
# ---- Architecture-specific target and flags ----
if(TARGET_ARCH STREQUAL "amd64")
    set(LIBVPX_TARGET "x86_64-win64-vs17")
    set(LIBVPX_ARCH_FLAGS "")
elseif(TARGET_ARCH STREQUAL "x86")
    set(LIBVPX_TARGET "x86-win32-vs17")
    set(LIBVPX_ARCH_FLAGS "")
elseif(TARGET_ARCH STREQUAL "arm")
    set(LIBVPX_TARGET "armv7-win32-vs17")
    set(LIBVPX_ARCH_FLAGS "--disable-neon --disable-thumb")
elseif(TARGET_ARCH STREQUAL "arm64")
    set(LIBVPX_TARGET "arm64-win64-vs17")
    set(LIBVPX_ARCH_FLAGS "--disable-neon --disable-thumb")
else()
    message(FATAL_ERROR "Unsupported TARGET_ARCH for libvpx: ${TARGET_ARCH}")
endif()

function(build_libvpx)
    ExternalProject_Add(libvpx_target
        URL          ${LIBVPX_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/libvpx"
        PATCH_COMMAND ${LIBVPX_RESOLVED_PATCH_CMDS}
        BUILD_IN_SOURCE 1
            CONFIGURE_COMMAND
                ${SHELL_COMPAT_ENV} 
                "TMPDIR=<SOURCE_DIR>"
                ./configure
                --prefix=${STAGE_DIR}
                --target=${LIBVPX_TARGET}
                --enable-static
                --disable-shared
                --disable-examples
                --disable-tools
                --disable-docs
                --disable-unit-tests
                --disable-dependency-tracking
                --as=yasm ${LIBVPX_ARCH_FLAGS}
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/vpx.lib"
            "${STAGE_DIR}/lib/pkgconfig/vpx.pc"
    )
    
    ExternalProject_Add_Step(libvpx_target rename
        COMMAND ${CMAKE_COMMAND} -E 
            rename 
            ${STAGE_DIR}/lib/libvpx.a 
            ${STAGE_DIR}/lib/vpx.lib
        DEPENDEES install
    )
endfunction()
