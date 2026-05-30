# ---- Registration ----
dep_package(
    NAME        opus
    DEFAULT     1.5.2
    BUILD       cmake
    FFMPEG_FLAG --enable-libopus
)
dep_package_version(NAME opus VERSION 1.5.2
    URL "https://github.com/xiph/opus/archive/refs/tags/v1.5.2.tar.gz"
)

# ---- Build function ----
function(build_opus)
    ExternalProject_Add(opus_target
        URL          ${OPUS_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/opus"
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/opus.lib"
            "${STAGE_DIR}/lib/pkgconfig/opus.pc"
    )
endfunction()
