# ---- Registration ----
dep_package(
    NAME        openjpeg
    DEFAULT     2.5.4
    BUILD       cmake
    FFMPEG_FLAG --enable-libopenjpeg
)
dep_package_version(NAME openjpeg VERSION 2.5.4
    URL "https://github.com/uclouvain/openjpeg/archive/refs/tags/v2.5.4.tar.gz"
)

# ---- Build function ----
function(build_openjpeg)
    skip_if_staged_target(openjpeg_target
        LIBS libopenjp2
    )
    ExternalProject_Add(openjpeg_target
        URL          ${OPENJPEG_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/openjpeg"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DBUILD_CODEC=OFF
            -DBUILD_TESTING=OFF
            -DBUILD_THIRDPARTY=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/openjp2.lib"
            "${STAGE_DIR}/lib/pkgconfig/libopenjp2.pc"
    )
endfunction()
