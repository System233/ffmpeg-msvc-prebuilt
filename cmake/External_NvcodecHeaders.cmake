# ---- Registration ----
dep_package(
    NAME        nvcodec
    DEFAULT     12.2.72.0
    BUILD       autotools
)
dep_package_version(NAME nvcodec VERSION 12.2.72.0
    URL "https://github.com/FFmpeg/nv-codec-headers/archive/refs/tags/n12.2.72.0.tar.gz"
)

# ---- Build function ----
function(build_nvcodec)
    skip_if_staged_target(nvcodec_target ffnvcodec)
    ExternalProject_Add(nvcodec_target
        URL          ${NVCODEC_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/nvcodec"
        CONFIGURE_COMMAND ""
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR> PREFIX=${STAGE_DIR}
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install PREFIX=${STAGE_DIR}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/include/nv-codec-headers/nvcuvid.h"
    )
endfunction()
