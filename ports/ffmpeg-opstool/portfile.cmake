set(VCPKG_POLICY_EMPTY_INCLUDE_FOLDER enabled)
set(VCPKG_BUILD_TYPE release)

vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO ffmpeg/ffmpeg
    REF "f760b2fb67"
    SHA512 e3b468972751a4c9905bfc969dfa16481ea4966092d7e71145070e3d74ba439c880ddc7db0d685166ce0292fad63e2e7c931fd95e127b3cbb744b4b2c70bf224
    HEAD_REF master
)

file(COPY "${CMAKE_CURRENT_LIST_DIR}/CMakeLists.txt" DESTINATION "${SOURCE_PATH}/libswscale/aarch64")

vcpkg_cmake_configure(
    SOURCE_PATH "${SOURCE_PATH}/libswscale/aarch64"
)

vcpkg_cmake_install()
vcpkg_copy_pdbs()

vcpkg_install_copyright(FILE_LIST "${SOURCE_PATH}/COPYING.LGPLv2.1")
