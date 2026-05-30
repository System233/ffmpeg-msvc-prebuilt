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
    PATCHES  x265/msvc-static-pkgconfig.patch;x265/msvc-shared-pkgconfig.patch;x265/arm-emms-fix.patch
)

# ---- Build function ----
# x265 source tarball has CMakeLists.txt in a "source/" subdirectory
function(build_x265)
    ExternalProject_Add(x265_target
        URL          ${X265_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/x265"
        SOURCE_SUBDIR "source"
        PATCH_COMMAND ${X265_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
                -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
                -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
                -DCMAKE_BUILD_TYPE=Release
                -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
                -DBUILD_SHARED_LIBS=OFF
                -DENABLE_CLI=OFF
                -DENABLE_SHARED=OFF
                -DSTATIC_LINK_CRT=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/x265.lib"
            "${STAGE_DIR}/lib/pkgconfig/x265.pc"
    )
endfunction()
