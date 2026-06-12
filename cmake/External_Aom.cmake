# ---- Registration ----
dep_package(
    NAME        aom
    DEFAULT     3.11.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libaom
)
dep_package_version(NAME aom VERSION 3.11.0
    URL "https://storage.googleapis.com/aom-releases/libaom-3.11.0.tar.gz"
    PATCHES aom/temporal_filter_neon.patch
)
if(TARGET_ARCH STREQUAL "amd64")
    set(AOM_FLAGS "-DENABLE_NASM=ON")
elseif(TARGET_ARCH STREQUAL "x86")
    set(AOM_FLAGS "-DENABLE_NASM=ON")
elseif(TARGET_ARCH STREQUAL "arm")
    set(AOM_FLAGS "-DENABLE_NASM=OFF")
elseif(TARGET_ARCH STREQUAL "arm64")
    set(AOM_FLAGS "-DENABLE_NASM=OFF")
else()
    message(FATAL_ERROR "Unsupported TARGET_ARCH for libvpx: ${TARGET_ARCH}")
endif()
# ---- Build function ----
function(build_aom)
    skip_if_staged_target(aom_target
        LIBS aom
    )
    ExternalProject_Add(aom_target
        URL          ${AOM_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/aom"
        PATCH_COMMAND ${AOM_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DENABLE_TESTS=OFF
            -DENABLE_DOCS=OFF
            -DENABLE_EXAMPLES=OFF
            -DENABLE_NASM=ON
            -DAOM_TARGET_CPU=${TARGET_ARCH}
            -DENABLE_TOOLS=OFF
            ${AOM_FLAGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/aom.lib"
            "${STAGE_DIR}/lib/pkgconfig/aom.pc"
    )
    add_pkgconfig_file(aom_target aom.pc aom 3.11.0 "AV1 codec library")
endfunction()
