# ---- Registration ----
dep_package(
    NAME        x265
    DEFAULT     4.1
    BUILD       cmake
    FFMPEG_FLAG --enable-libx265
    LICENSE     gpl
)
dep_package_version(NAME x265 VERSION 4.1
    URL      "https://bitbucket.org/multicoreware/x265_git/downloads/x265_4.1.tar.gz"
    PATCHES   x265/arm-emms-fix.patch;x265/cmake-policy.patch
)
if(TARGET_ARCH STREQUAL "amd64")
    # set(X265_BUILD_FLAGS)
elseif(TARGET_ARCH STREQUAL "x86")
    # set(X265_BUILD_FLAGS)
elseif(TARGET_ARCH STREQUAL "arm")
    # set(X265_BUILD_FLAGS)
elseif(TARGET_ARCH STREQUAL "arm64")
    set(X265_BUILD_FLAGS 
            -DENABLE_ASSEMBLY=OFF
    )
else()
    message(FATAL_ERROR "Unsupported TARGET_ARCH for libvpx: ${TARGET_ARCH}")
endif()
# ---- Build function ----
# x265 source tarball has CMakeLists.txt in a "source/" subdirectory
function(build_x265)
    skip_if_staged_target(x265_target LIBS x265)
    ExternalProject_Add(x265_target
        URL          ${X265_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/x265"
        SOURCE_SUBDIR "source"
        PATCH_COMMAND ${X265_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
                ${DEPS_CMAKE_ARGS}
                -DENABLE_CLI=OFF
                -DENABLE_SHARED=OFF
                -DSTATIC_LINK_CRT=ON
                -DENABLE_HDR10_PLUS=ON
                ${X265_BUILD_FLAGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/x265.lib"
            "${STAGE_DIR}/lib/pkgconfig/x265.pc"
    )
    ExternalProject_Add_Step(x265_target rename
        COMMAND ${CMAKE_COMMAND} -E 
            rename 
            ${STAGE_DIR}/lib/x265-static.lib 
            ${STAGE_DIR}/lib/x265.lib
        DEPENDEES install
    )
endfunction()
