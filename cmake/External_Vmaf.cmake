# ---- Registration ----
dep_package(
    NAME        vmaf
    DEFAULT     3.1.0
    BUILD       meson
    FFMPEG_FLAG --enable-libvmaf
    REQUIRES    pthreads
)
dep_package_version(NAME vmaf VERSION 3.1.0
    URL "https://github.com/Netflix/vmaf/archive/refs/tags/v3.1.0.tar.gz"
)

# ---- Build function ----
function(build_vmaf)
    set(VMAF_C_ARGS "${CMAKE_C_FLAGS} /experimental:c11atomics /I${STAGE_DIR}/include")
    set(VMAF_CXX_ARGS "${CMAKE_CXX_FLAGS} /experimental:c11atomics /I${STAGE_DIR}/include")

    set(VMAF_C_LINK_ARGS  "/LIBPATH:${STAGE_DIR}/lib pthreadVSE3.lib")
    set(VMAF_CXX_LINK_ARGS "/LIBPATH:${STAGE_DIR}/lib pthreadVSE3.lib")


    ExternalProject_Add(vmaf_target
        DEPENDS      ${VMAF_RESOLVED_DEPENDS}
        URL          ${VMAF_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/vmaf"
        CONFIGURE_COMMAND
            ${SHELL_ENV} meson setup <BINARY_DIR> <SOURCE_DIR>/libvmaf
                "-Dc_args=[\"${CMAKE_C_FLAGS}\",\"/experimental:c11atomics\",\"/I${STAGE_DIR}/include\"]"
                # -Dc_link_args=[${VMAF_C_LINK_ARGS}]
                # -Dcpp_link_args=[${VMAF_CXX_LINK_ARGS}]
                -Db_vscrt=mt
                --prefix=${STAGE_DIR}
                --buildtype=release
                --default-library=static
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
                -Denable_tests=false
                -Denable_tools=false
                -Denable_docs=false
                -Denable_avx512=false 
        BUILD_COMMAND   meson compile -C <BINARY_DIR>
        INSTALL_COMMAND meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/vmaf.lib"
            "${STAGE_DIR}/lib/pkgconfig/libvmaf.pc"
    )
    add_rename_step(vmaf_target libvmaf.a vmaf.lib)
endfunction()
