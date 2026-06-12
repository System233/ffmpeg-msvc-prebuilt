# ---- Registration ----
dep_package(
    NAME        codec2
    DEFAULT     1.2.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libcodec2
)
dep_package_version(NAME codec2 VERSION 1.2.0
    URL      "https://github.com/drowe67/codec2/archive/refs/tags/1.2.0.tar.gz"
    PATCHES  codec2/msvc-exe-suffix.patch;codec2/msvc-gcc-flags.patch
)

# ---- Build function ----
function(build_codec2)
    skip_if_staged_target(codec2_target LIBS codec2)
    ExternalProject_Add(codec2_target
        DEPENDS      ${CODEC2_RESOLVED_DEPENDS}
        URL          ${CODEC2_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/codec2"
        PATCH_COMMAND ${CODEC2_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DUNITTEST=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/codec2.lib"
            "${STAGE_DIR}/lib/pkgconfig/codec2.pc"
    )
endfunction()
