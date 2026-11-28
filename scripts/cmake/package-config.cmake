# Generate both discovery modes from the same implementation and metadata.
include(CMakePackageConfigHelpers)

function(ffmpeg_install_cmake_package destination)
    configure_file("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/FindFFmpeg.cmake.in"
                   "${destination}/FindFFmpeg.cmake" @ONLY)
    # The compatibility entry is also the shared implementation. Keeping
    # a single copy makes mixed MODULE/CONFIG calls share the SDK identity.
    file(WRITE "${destination}/FFmpegConfig.cmake" [=[
set(_ffmpeg_config_mode TRUE)
include("${CMAKE_CURRENT_LIST_DIR}/FindFFmpeg.cmake")
unset(_ffmpeg_config_mode)
]=])
    # Compatibility for uppercase find_package(FFMPEG MODULE) on
    # case-sensitive hosts. Do not create a case-colliding Windows file.
    if(NOT CMAKE_HOST_WIN32)
        file(WRITE "${destination}/FindFFMPEG.cmake" [=[
include("${CMAKE_CURRENT_LIST_DIR}/FindFFmpeg.cmake")
]=])
    endif()

    # vcpkg runs in script mode; derive pointer width from the target,
    # never from the host. CMake checks width, not CPU architecture.
    if(VCPKG_TARGET_ARCHITECTURE MATCHES "^(x64|arm64|s390x|ppc64le|riscv64)$")
        set(CMAKE_SIZEOF_VOID_P 8)
    elseif(VCPKG_TARGET_ARCHITECTURE MATCHES "^(x86|arm|wasm32)$")
        set(CMAKE_SIZEOF_VOID_P 4)
    else()
        unset(CMAKE_SIZEOF_VOID_P)
    endif()
    # Preserve the established minimum-version semantics of FindFFmpeg.
    # This is version selection, not an ABI compatibility guarantee.
    write_basic_package_version_file("${destination}/FFmpegConfigVersion.cmake"
        VERSION "${FFMPEG_VERSION}" COMPATIBILITY AnyNewerVersion)
endfunction()
