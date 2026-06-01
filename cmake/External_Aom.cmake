# ---- Registration ----
dep_package(
    NAME        aom
    DEFAULT     3.11.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libaom
)
dep_package_version(NAME aom VERSION 3.11.0
    URL "https://storage.googleapis.com/aom-releases/libaom-3.11.0.tar.gz"
)

# ---- Build function ----
function(build_aom)
    ExternalProject_Add(aom_target
        URL          ${AOM_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/aom"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DENABLE_TESTS=OFF
            -DENABLE_DOCS=OFF
            -DENABLE_EXAMPLES=OFF
            -DENABLE_NASM=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/aom.lib"
            "${STAGE_DIR}/lib/pkgconfig/aom.pc"
    )
    add_pkgconfig_file(aom_target aom.pc aom 3.11.0 "AV1 codec library")
endfunction()
