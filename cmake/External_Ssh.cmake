# ---- Registration ----
dep_package(
    NAME        ssh
    DEFAULT     0.11.4
    BUILD       cmake
    FFMPEG_FLAG --enable-libssh
    REQUIRES    mbedtls
)
dep_package_version(NAME ssh VERSION 0.11.4
    URL "https://www.libssh.org/files/0.11/libssh-0.11.4.tar.xz"
    # PATCHES ssh/libssh_static.patch
)

# ---- Build function ----
function(build_ssh)
    skip_if_staged_target(ssh_target
        LIBS libssh
    )
    ExternalProject_Add(ssh_target
        DEPENDS      ${SSH_RESOLVED_DEPENDS}
        URL          ${SSH_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/ssh"
        PATCH_COMMAND ${SSH_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DWITH_ZLIB=ON
            -DWITH_SFTP=ON
            -DWITH_SERVER=OFF
            -DWITH_GSSAPI=OFF
            -DWITH_SYMBOL_VERSIONING=OFF
            -DWITH_EXAMPLES=OFF
            -DUNIT_TESTING=OFF
            -DWITH_GCRYPT=OFF
            -DWITH_MBEDTLS=ON
            -DBUILD_STATIC_LIB=ON
            
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/ssh.lib"
            "${STAGE_DIR}/lib/pkgconfig/libssh.pc"
    )
    add_pkgconfig_file(ssh_target libssh.pc ssh 0.11.4 "SSH library" 
            CFLAGS "-DLIBSSH_STATIC"
            REQUIRES        mbedtls
                            mbedx509
                            mbedcrypto
                            zlib;
            LIBS_PRIVATE    ws2_32
                            advapi32
                            shell32
                            iphlpapi
                            bcrypt
    )
endfunction()
