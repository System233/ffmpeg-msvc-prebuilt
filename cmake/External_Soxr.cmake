# ---- Registration ----
dep_package(
    NAME        soxr
    DEFAULT     0.1.3
    BUILD       cmake
    FFMPEG_FLAG --enable-libsoxr
)
dep_package_version(NAME soxr VERSION 0.1.3
    URL "https://downloads.sourceforge.net/project/soxr/soxr-0.1.3-Source.tar.xz"
    PATCHES soxr/enable_pc.patch
)

# ---- Build function ----
function(build_soxr)
    ExternalProject_Add(soxr_target
        URL          ${SOXR_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/soxr"
        PATCH_COMMAND ${SOXR_RESOLVED_PATCH_CMDS}

        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/soxr.lib"
            "${STAGE_DIR}/lib/pkgconfig/soxr.pc"
    )
endfunction()
