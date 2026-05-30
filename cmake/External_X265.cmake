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
                -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
                -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER}
                -DCMAKE_BUILD_TYPE=Release
                -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
                -DBUILD_SHARED_LIBS=OFF
                -DENABLE_CLI=OFF
                -DENABLE_SHARED=OFF
                -DSTATIC_LINK_CRT=ON
                -DCMAKE_SYSTEM_NAME=Windows
                -DCMAKE_POLICY_VERSION_MINIMUM=3.5
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
