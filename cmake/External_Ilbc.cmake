# ---- Registration ----
dep_package(
    NAME        ilbc
    DEFAULT     3.0.4
    BUILD       cmake
    FFMPEG_FLAG --enable-libilbc
)
dep_package_version(NAME ilbc VERSION 3.0.4
    URL "https://github.com/TimothyGu/libilbc/archive/refs/tags/v3.0.4.tar.gz"
)

# ---- Build function ----
function(build_ilbc)
    skip_if_staged_target(ilbc_target
        LIBS libilbc
    )
    ExternalProject_Add(ilbc_target
        URL          ${ILBC_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/ilbc"
        PATCH_COMMAND ${ILBC_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            "-DCMAKE_ASM_MASM_COMPILER="
            "-DCMAKE_ASM_COMPILER="
            "-DCMAKE_MSVC_RUNTIME_LIBRARY="
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/ilbc.lib"
            "${STAGE_DIR}/lib/pkgconfig/libilbc.pc"
    )
endfunction()
