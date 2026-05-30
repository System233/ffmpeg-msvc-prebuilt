ExternalProject_Add(zlib_target
    URL            https://github.com/madler/zlib/archive/refs/tags/v1.3.1.tar.gz
    DOWNLOAD_DIR   "${CMAKE_CURRENT_BINARY_DIR}/downloads"
    SOURCE_DIR     "${CMAKE_CURRENT_BINARY_DIR}/src/zlib"
        
    PATCH_COMMAND
        patch -p1 -d <SOURCE_DIR> -i "${CMAKE_CURRENT_LIST_DIR}/../patches/zlib/msvc-shared-libs.patch"

    CMAKE_ARGS
        -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
        -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
        -DBUILD_SHARED_LIBS=OFF
        -DZLIB_BUILD_EXAMPLES=OFF

    BUILD_BYPRODUCTS
        "${STAGE_DIR}/lib/zlib.lib"
        "${STAGE_DIR}/lib/pkgconfig/zlib.pc"
)
