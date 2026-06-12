# ---- Registration ----
dep_package(
    NAME        pthreads
    DEFAULT     4.1.0.0
    BUILD       cmake
)
dep_package_version(NAME pthreads VERSION 4.1.0.0
    URL "https://github.com/GerHobbelt/pthread-win32/archive/refs/tags/v4.1.0.0.tar.gz"
)

# ---- Build function ----
function(build_pthreads)
    skip_if_staged_target(pthreads_target FILES "${STAGE_DIR}/lib/pthreadVSE3.lib" "${STAGE_DIR}/include/pthread.h")
    ExternalProject_Add(pthreads_target
        URL          ${PTHREADS_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/pthreads"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/pthreadVSE3.lib"
            "${STAGE_DIR}/include/pthread.h"
    )
    add_rename_step(pthreads_target pthreadVSE3.lib pthread.lib)
    add_pkgconfig_file(pthreads_target pthread.pc pthread 4.1.0 "POSIX Threads for Windows")
endfunction()
