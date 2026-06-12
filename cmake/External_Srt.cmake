# ---- Registration ----
dep_package(
    NAME        srt
    DEFAULT     1.5.4
    BUILD       cmake
    FFMPEG_FLAG --enable-libsrt
)
dep_package_version(NAME srt VERSION 1.5.4
    URL "https://github.com/Haivision/srt/archive/refs/tags/v1.5.4.tar.gz"
)

# ---- Build function ----
function(build_srt)
    skip_if_staged_target(srt_target
        LIBS srt
    )
    ExternalProject_Add(srt_target
        URL          ${SRT_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/srt"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DENABLE_SHARED=OFF
            -DENABLE_STATIC=ON
            -DENABLE_ENCRYPTION=OFF
            -DENABLE_APPS=OFF
            -DENABLE_CXX_DEPS=ON
            -DENABLE_STDCXX_SYNC=ON
            -DENABLE_TESTING=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/srt.lib"
            "${STAGE_DIR}/lib/pkgconfig/srt.pc"
    )
    
    ExternalProject_Add_Step(srt_target rename
        COMMAND ${CMAKE_COMMAND} -E 
            rename 
            "${STAGE_DIR}/lib/srt_static.lib"
            "${STAGE_DIR}/lib/srt.lib"
        DEPENDEES install
    )
endfunction()
