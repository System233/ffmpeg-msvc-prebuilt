# ffmpeg-builder.cmake
#
# Shared CMake build base class for FFmpeg vcpkg ports.
#
# Per-version portfile.cmake must set these variables before include():
#   FFMPEG_VERSION   - FFmpeg upstream version string (e.g. "8.1.1")
#   FFMPEG_SHA512    - Source tarball SHA512 checksum
#   FFMPEG_PATCHES   - List of patch file names (relative to port directory)
#   FFMPEG_PATCHES_DIR - Patches directory (e.g. ${CMAKE_CURRENT_LIST_DIR}/../../patches/8.x)
#   CURRENT_PORT_DIR  - ${CMAKE_CURRENT_LIST_DIR} of the calling portfile.cmake
#
# Example caller:
#   set(FFMPEG_VERSION "8.1.1")
#   set(FFMPEG_SHA512 "e858e92e...")
#   set(FFMPEG_PATCHES
#       0002-fix-msvc-link.patch
#       0003-fix-windowsinclude.patch
#       ...)
#   set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
#   include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-builder.cmake")
#
# This base class handles: source download, toolchain config, configure flags,
# Release+Debug dual build, DEF→LIB generation, pkgconfig fixup, install,
# FindFFMPEG.cmake generation, and copyright.

set(FFMPEG_SHARED_DIR ${CMAKE_CURRENT_LIST_DIR})

# ---- Guard ----
if(DEFINED __FFMPEG_PORT_BASE_INCLUDED)
    return()
endif()
set(__FFMPEG_PORT_BASE_INCLUDED TRUE)

# ---- Macros: feature → flag mapping ----
# ffmpeg_feature(name "--flag1" "--flag2" ...)
#   If feature "name" is in FEATURES list, append all given flags to OPTIONS.
macro(ffmpeg_feature _name)
    if("${_name}" IN_LIST FEATURES)
        foreach(_f ${ARGN})
            set(OPTIONS "${OPTIONS} ${_f}")
            string(TOUPPER "${_name}" _uc)
            set(ENABLE_${_uc} ON)
        endforeach()
    endif()
endmacro()

# ffmpeg_feature_core(name "--flag" pkg_module)
#   Variant for core modules: also sets ENABLE_<NAME> and adds pkgconfig module.
macro(ffmpeg_feature_core _name _flag _pkgmod)
    if("${_name}" IN_LIST FEATURES)
        set(OPTIONS "${OPTIONS} ${_flag}")
        string(TOUPPER "${_name}" _uc)
        set(ENABLE_${_uc} ON)
        list(APPEND FFMPEG_PKGCONFIG_MODULES ${_pkgmod})
    endif()
endmacro()

# ffmpeg_feature_core_multi(name "--flag" pkg_module)
#   Same but use the name as-is for ENABLE_* and pkg module (for multi-word names).
macro(ffmpeg_feature_core_multi _name _flag _pkgmod)
    if("${_name}" IN_LIST FEATURES)
        set(OPTIONS "${OPTIONS} ${_flag}")
        set(${_pkgmod}_ON ON)
        list(APPEND FFMPEG_PKGCONFIG_MODULES ${_pkgmod})
    endif()
endmacro()

# ---- Required variables check ----
foreach(_required_var FFMPEG_VERSION FFMPEG_SHA512 FFMPEG_PATCHES_DIR CURRENT_PORT_DIR)
    if(NOT DEFINED ${_required_var})
        message(FATAL_ERROR "ffmpeg-builder.cmake: required variable ${_required_var} is not set. "
                            "Set it before include().")
    endif()
endforeach()

# ========== 1. Source download ==========

# Resolve patch paths relative to the caller's port directory
set(_FFMPEG_ABSOLUTE_PATCHES "")
foreach(_patch IN LISTS FFMPEG_PATCHES)
    if(IS_ABSOLUTE "${_patch}")
        list(APPEND _FFMPEG_ABSOLUTE_PATCHES "${_patch}")
    else()
        list(APPEND _FFMPEG_ABSOLUTE_PATCHES "${FFMPEG_PATCHES_DIR}/${_patch}")
    endif()
endforeach()

vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO ffmpeg/ffmpeg
    REF "n${FFMPEG_VERSION}"
    SHA512 "${FFMPEG_SHA512}"
    HEAD_REF master
    PATCHES ${_FFMPEG_ABSOLUTE_PATCHES}
)

# ========== 2. Path-space check + NASM ==========

if(SOURCE_PATH MATCHES " ")
    message(FATAL_ERROR "Error: ffmpeg will not build with spaces in the path. "
                        "Please use a directory with no spaces")
endif()

# ffmpeg-bin2c bin2c path: only needed for 8.1+ (uses prebuilt-bin2c patch)
if(DEFINED FFMPEG_NEED_BIN2C AND FFMPEG_NEED_BIN2C)
    vcpkg_add_to_path(PREPEND "${CURRENT_HOST_INSTALLED_DIR}/manual-tools/ffmpeg-bin2c")
endif()

if(VCPKG_TARGET_ARCHITECTURE STREQUAL "x86" OR VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
    vcpkg_find_acquire_program(NASM)
    get_filename_component(NASM_EXE_PATH "${NASM}" DIRECTORY)
    vcpkg_add_to_path("${NASM_EXE_PATH}")
endif()

# ========== 3. Initial OPTIONS + Platform detection ==========

set(OPTIONS "--enable-version3 --enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect")

if(DEFINED FFMPEG_BASE_OPTIONS)
    string(APPEND OPTIONS " ${FFMPEG_BASE_OPTIONS}")
endif()

if(VCPKG_TARGET_IS_MINGW)
    if(VCPKG_TARGET_ARCHITECTURE STREQUAL "x86")
        string(APPEND OPTIONS " --target-os=mingw32")
    elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
        string(APPEND OPTIONS " --target-os=mingw64")
    endif()
elseif(VCPKG_TARGET_IS_LINUX)
    string(APPEND OPTIONS " --target-os=linux --enable-pthreads")
elseif(VCPKG_TARGET_IS_UWP)
    string(APPEND OPTIONS " --target-os=win32")
elseif(VCPKG_TARGET_IS_WINDOWS)
    string(APPEND OPTIONS " --target-os=win32")
elseif(VCPKG_TARGET_IS_OSX)
    string(APPEND OPTIONS " --target-os=darwin --enable-appkit --enable-avfoundation --enable-coreimage --enable-audiotoolbox --enable-videotoolbox")
elseif(VCPKG_TARGET_IS_IOS)
    string(APPEND OPTIONS " --enable-avfoundation --enable-coreimage --enable-videotoolbox")
elseif(VCPKG_CMAKE_SYSTEM_NAME STREQUAL "Android")
    string(APPEND OPTIONS " --target-os=android --enable-jni --enable-mediacodec")
elseif(VCPKG_CMAKE_SYSTEM_NAME STREQUAL "QNX")
    string(APPEND OPTIONS " --target-os=qnx")
endif()

if(VCPKG_TARGET_IS_OSX)
    list(JOIN VCPKG_OSX_ARCHITECTURES " " OSX_ARCHS)
    list(LENGTH VCPKG_OSX_ARCHITECTURES OSX_ARCH_COUNT)
endif()

# ========== 4. MSVC toolchain detection ==========

vcpkg_cmake_get_vars(cmake_vars_file)
include("${cmake_vars_file}")
if(VCPKG_DETECTED_MSVC)
    set(OPTIONS "--toolchain=msvc ${OPTIONS}")
    # This is required because ffmpeg depends upon optimizations to link correctly
    string(APPEND VCPKG_COMBINED_C_FLAGS_DEBUG " -O2")
    string(REGEX REPLACE "(^| )-RTC1( |$)" " " VCPKG_COMBINED_C_FLAGS_DEBUG "${VCPKG_COMBINED_C_FLAGS_DEBUG}")
    string(REGEX REPLACE "(^| )-Od( |$)" " " VCPKG_COMBINED_C_FLAGS_DEBUG "${VCPKG_COMBINED_C_FLAGS_DEBUG}")
    string(REGEX REPLACE "(^| )-Ob0( |$)" " " VCPKG_COMBINED_C_FLAGS_DEBUG "${VCPKG_COMBINED_C_FLAGS_DEBUG}")
endif()

string(APPEND VCPKG_COMBINED_C_FLAGS_DEBUG " -I \"${CURRENT_INSTALLED_DIR}/include\"")
string(APPEND VCPKG_COMBINED_C_FLAGS_RELEASE " -I \"${CURRENT_INSTALLED_DIR}/include\"")

# ========== 5. Toolchain: CC/CXX/RC/LD/NM/AR/RANLIB/STRIP ==========

set(prog_env "")

if(VCPKG_DETECTED_CMAKE_C_COMPILER)
    get_filename_component(CC_path "${VCPKG_DETECTED_CMAKE_C_COMPILER}" DIRECTORY)
    get_filename_component(CC_filename "${VCPKG_DETECTED_CMAKE_C_COMPILER}" NAME)
    set(ENV{CC} "${CC_filename}")
    string(APPEND OPTIONS " --cc=${CC_filename}")
    list(APPEND prog_env "${CC_path}")
endif()

if(VCPKG_DETECTED_CMAKE_CXX_COMPILER)
    get_filename_component(CXX_path "${VCPKG_DETECTED_CMAKE_CXX_COMPILER}" DIRECTORY)
    get_filename_component(CXX_filename "${VCPKG_DETECTED_CMAKE_CXX_COMPILER}" NAME)
    set(ENV{CXX} "${CXX_filename}")
    string(APPEND OPTIONS " --cxx=${CXX_filename}")
    list(APPEND prog_env "${CXX_path}")
endif()

if(VCPKG_DETECTED_CMAKE_RC_COMPILER)
    get_filename_component(RC_path "${VCPKG_DETECTED_CMAKE_RC_COMPILER}" DIRECTORY)
    get_filename_component(RC_filename "${VCPKG_DETECTED_CMAKE_RC_COMPILER}" NAME)
    set(ENV{WINDRES} "${RC_filename}")
    string(APPEND OPTIONS " --windres=${RC_filename}")
    list(APPEND prog_env "${RC_path}")
endif()

if(VCPKG_DETECTED_CMAKE_LINKER AND VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
    get_filename_component(LD_path "${VCPKG_DETECTED_CMAKE_LINKER}" DIRECTORY)
    get_filename_component(LD_filename "${VCPKG_DETECTED_CMAKE_LINKER}" NAME)
    set(ENV{LD} "${LD_filename}")
    string(APPEND OPTIONS " --ld=${LD_filename}")
    list(APPEND prog_env "${LD_path}")
endif()

if(VCPKG_DETECTED_CMAKE_NM)
    get_filename_component(NM_path "${VCPKG_DETECTED_CMAKE_NM}" DIRECTORY)
    get_filename_component(NM_filename "${VCPKG_DETECTED_CMAKE_NM}" NAME)
    set(ENV{NM} "${NM_filename}")
    string(APPEND OPTIONS " --nm=${NM_filename}")
    list(APPEND prog_env "${NM_path}")
endif()

if(VCPKG_DETECTED_CMAKE_AR)
    get_filename_component(AR_path "${VCPKG_DETECTED_CMAKE_AR}" DIRECTORY)
    get_filename_component(AR_filename "${VCPKG_DETECTED_CMAKE_AR}" NAME)
    if(AR_filename MATCHES [[^(llvm-)?lib\.exe$]])
        set(ENV{AR} "ar-lib ${AR_filename}")
        string(APPEND OPTIONS " --ar='ar-lib ${AR_filename}'")
    else()
        set(ENV{AR} "${AR_filename}")
        string(APPEND OPTIONS " --ar='${AR_filename}'")
    endif()
    list(APPEND prog_env "${AR_path}")
endif()

if(VCPKG_DETECTED_CMAKE_RANLIB)
    get_filename_component(RANLIB_path "${VCPKG_DETECTED_CMAKE_RANLIB}" DIRECTORY)
    get_filename_component(RANLIB_filename "${VCPKG_DETECTED_CMAKE_RANLIB}" NAME)
    set(ENV{RANLIB} "${RANLIB_filename}")
    string(APPEND OPTIONS " --ranlib=${RANLIB_filename}")
    list(APPEND prog_env "${RANLIB_path}")
endif()

if(VCPKG_DETECTED_CMAKE_STRIP)
    get_filename_component(STRIP_path "${VCPKG_DETECTED_CMAKE_STRIP}" DIRECTORY)
    get_filename_component(STRIP_filename "${VCPKG_DETECTED_CMAKE_STRIP}" NAME)
    set(ENV{STRIP} "${STRIP_filename}")
    string(APPEND OPTIONS " --strip=${STRIP_filename}")
    list(APPEND prog_env "${STRIP_path}")
endif()

# ========== 6. MSYS2 / bash setup ==========

if(VCPKG_HOST_IS_WINDOWS)
    vcpkg_acquire_msys(MSYS_ROOT PACKAGES automake)
    set(SHELL "${MSYS_ROOT}/usr/bin/bash.exe")
    vcpkg_execute_required_process(
        COMMAND "${SHELL}" -c "'/usr/bin/automake' --print-lib"
        OUTPUT_VARIABLE automake_lib
        OUTPUT_STRIP_TRAILING_WHITESPACE
        WORKING_DIRECTORY "${MSYS_ROOT}"
        LOGNAME automake-print-lib
    )
    list(APPEND prog_env "${MSYS_ROOT}/usr/bin" "${MSYS_ROOT}${automake_lib}")
else()
    find_program(SHELL bash)
endif()

list(REMOVE_DUPLICATES prog_env)
vcpkg_add_to_path(PREPEND ${prog_env})

# ========== 7. Clean build dirs + init pkgconfig modules ==========

file(REMOVE_RECURSE
    "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-dbg"
    "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-rel"
)

set(FFMPEG_PKGCONFIG_MODULES libavutil)

# ========== 8b. Feature → --enable-* flag mapping ==========
# Generated from base.yaml by scripts/generate.py.
# The base cmake has NO knowledge of FFmpeg versions; features alone control
# what is enabled.

include("${CURRENT_PORT_DIR}/features.cmake")

# ========== 10. Programs: always enabled (except UWP) ==========

if(VCPKG_TARGET_IS_UWP)
    set(OPTIONS "${OPTIONS} --disable-programs")
else()
    set(OPTIONS "${OPTIONS} --enable-ffmpeg --enable-ffplay --enable-ffprobe")
endif()

# ========== 11. Cross-compile + BUILD_ARCH ==========

set(OPTIONS_CROSS "--enable-cross-compile")

if(VCPKG_DETECTED_CMAKE_C_COMPILER MATCHES "([^\/]*-)gcc$")
    string(APPEND OPTIONS_CROSS " --cross-prefix=${CMAKE_MATCH_1}")
endif()

if(VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
    set(BUILD_ARCH "x86_64")
else()
    set(BUILD_ARCH ${VCPKG_TARGET_ARCHITECTURE})
endif()

# ========== 12. ARM gas preprocessor ==========

if(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm" OR VCPKG_TARGET_ARCHITECTURE STREQUAL "arm64")
    if(VCPKG_TARGET_IS_WINDOWS)
        vcpkg_find_acquire_program(GASPREPROCESSOR)
        foreach(GAS_PATH ${GASPREPROCESSOR})
            get_filename_component(GAS_ITEM_PATH ${GAS_PATH} DIRECTORY)
            vcpkg_add_to_path("${GAS_ITEM_PATH}")
        endforeach()
    endif()
endif()

# ========== 13. UWP-specific handling ==========

if(VCPKG_TARGET_IS_UWP)
    set(ENV{LIBPATH} "$ENV{LIBPATH};$ENV{_WKITS10}references\\windows.foundation.foundationcontract\\2.0.0.0\\;$ENV{_WKITS10}references\\windows.foundation.universalapicontract\\3.0.0.0\\")
    string(APPEND OPTIONS " --extra-cflags=-DWINAPI_FAMILY=WINAPI_FAMILY_APP --extra-cflags=-D_WIN32_WINNT=0x0A00")
    string(APPEND OPTIONS " --extra-ldflags=-APPCONTAINER --extra-ldflags=WindowsApp.lib --extra-ldflags=dxguid.lib")
endif()

# ========== 14. iOS handling ==========

if(VCPKG_TARGET_IS_IOS)
    set(vcpkg_target_arch "${VCPKG_TARGET_ARCHITECTURE}")
    if(VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
        set(vcpkg_target_arch "x86_64")
    elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm")
        message(FATAL_ERROR "You can build for arm up to iOS 10 but ffmpeg can only be built for iOS 11.0 and later. "
                            "Did you mean arm64?")
    elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "x86")
        message(FATAL_ERROR "You can build for x86 up to iOS 10 but ffmpeg can only be built for iOS 11.0 and later. "
                            "Did you mean x64")
    endif()

    set(vcpkg_osx_deployment_target "${VCPKG_OSX_DEPLOYMENT_TARGET}")
    if(NOT VCPKG_OSX_DEPLOYMENT_TARGET)
        set(vcpkg_osx_deployment_target 11.0)
    elseif(VCPKG_OSX_DEPLOYMENT_TARGET LESS 11.0)
        message(FATAL_ERROR "ffmpeg can be built only for iOS 11.0 and later but you set VCPKG_OSX_DEPLOYMENT_TARGET to "
                            "${VCPKG_OSX_DEPLOYMENT_TARGET}")
    endif()

    if(VCPKG_OSX_SYSROOT STREQUAL "iphonesimulator")
        set(simulator "-simulator")
    endif()

    set(OPTIONS "${OPTIONS} --extra-cflags=--target=${vcpkg_target_arch}-apple-ios${vcpkg_osx_deployment_target}${simulator}")
    set(OPTIONS "${OPTIONS} --extra-ldflags=--target=${vcpkg_target_arch}-apple-ios${vcpkg_osx_deployment_target}${simulator}")

    set(vcpkg_osx_sysroot "${VCPKG_OSX_SYSROOT}")
    if((VCPKG_OSX_SYSROOT MATCHES "^(iphoneos|iphonesimulator)$") OR (NOT VCPKG_OSX_SYSROOT) OR (VCPKG_OSX_SYSROOT STREQUAL ""))
        if(VCPKG_OSX_SYSROOT MATCHES "^(iphoneos|iphonesimulator)$")
            set(requested_sysroot "${VCPKG_OSX_SYSROOT}")
        elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm64")
            set(requested_sysroot "iphoneos")
        elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
            set(requested_sysroot "iphonesimulator")
        else()
            message(FATAL_ERROR "Unsupported build arch: ${VCPKG_TARGET_ARCHITECTURE}")
        endif()
        message(STATUS "Retrieving default SDK for ${requested_sysroot}")
        execute_process(
            COMMAND /usr/bin/xcrun --sdk ${requested_sysroot} --show-sdk-path
            OUTPUT_VARIABLE sdk_path
            ERROR_VARIABLE xcrun_error
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_STRIP_TRAILING_WHITESPACE
        )
        if(sdk_path)
            message(STATUS "Found!")
            set(vcpkg_osx_sysroot "${sdk_path}")
        else()
            message(FATAL_ERROR "Can't determine ${CMAKE_OSX_SYSROOT} SDK path. Error: ${xcrun_error}")
        endif()
    endif()
    set(OPTIONS "${OPTIONS} --extra-cflags=-isysroot\"${vcpkg_osx_sysroot}\"")
    set(OPTIONS "${OPTIONS} --extra-ldflags=-isysroot\"${vcpkg_osx_sysroot}\"")
endif()

# ========== 15. CRT flags (MSVC) + Release/Debug OPTIONS ==========

set(OPTIONS_DEBUG "${FFMPEG_OPTIONS_DEBUG}")
set(OPTIONS_RELEASE "--enable-optimizations")

if(VCPKG_DETECTED_MSVC)
    set(FFMPEG_CRT_PREFIX "-MT")
    if(VCPKG_CRT_LINKAGE STREQUAL "dynamic")
        set(FFMPEG_CRT_PREFIX "-MD")
    endif()
    string(APPEND OPTIONS_RELEASE " --extra-cflags=${FFMPEG_CRT_PREFIX} --extra-cxxflags=${FFMPEG_CRT_PREFIX}")
    string(APPEND OPTIONS_DEBUG " --extra-cflags=${FFMPEG_CRT_PREFIX}d --extra-cxxflags=${FFMPEG_CRT_PREFIX}d")
endif()

# ========== 16. Assemble final OPTIONS ==========

set(OPTIONS "${OPTIONS} ${OPTIONS_CROSS}")

if("static" IN_LIST FEATURES)
    set(OPTIONS "${OPTIONS} --disable-shared --enable-static")
else()
    set(OPTIONS "${OPTIONS} --disable-static --enable-shared")
endif()

if(VCPKG_TARGET_IS_MINGW)
    set(OPTIONS "${OPTIONS} --extra_cflags=-D_WIN32_WINNT=0x0601")
elseif(VCPKG_TARGET_IS_WINDOWS)
    set(OPTIONS "${OPTIONS} --extra-cflags=-DHAVE_UNISTD_H=0")
endif()

if(NOT VCPKG_TARGET_IS_WINDOWS)
    set(maybe_needed_libraries -lm)
else()
    set(maybe_needed_libraries "")
endif()

separate_arguments(standard_libraries NATIVE_COMMAND "${VCPKG_DETECTED_CMAKE_C_STANDARD_LIBRARIES}")
foreach(item IN LISTS standard_libraries)
    if(item IN_LIST maybe_needed_libraries)
        set(OPTIONS "${OPTIONS} \"--extra-libs=${item}\"")
    endif()
endforeach()

vcpkg_find_acquire_program(PKGCONFIG)
set(OPTIONS "${OPTIONS} --pkg-config=\"${PKGCONFIG}\"")


message(STATUS "Building Options: ${OPTIONS}")

# ========== 17. Release build ==========

if(NOT VCPKG_BUILD_TYPE OR VCPKG_BUILD_TYPE STREQUAL "release")
    if(VCPKG_DETECTED_MSVC)
        set(OPTIONS_RELEASE "${OPTIONS_RELEASE} --extra-ldflags=-libpath:\"${CURRENT_INSTALLED_DIR}/lib\"")
    else()
        set(OPTIONS_RELEASE "${OPTIONS_RELEASE} --extra-ldflags=-L\"${CURRENT_INSTALLED_DIR}/lib\"")
    endif()
    message(STATUS "Building Release Options: ${OPTIONS_RELEASE}")
    message(STATUS "Building ${PORT} for Release")
    file(MAKE_DIRECTORY "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-rel")

    set(crsp "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-rel/cflags.rsp")
    string(REGEX REPLACE "-arch [A-Za-z0-9_]+" "" VCPKG_COMBINED_C_FLAGS_RELEASE_SANITIZED "${VCPKG_COMBINED_C_FLAGS_RELEASE}")
    file(WRITE "${crsp}" "${VCPKG_COMBINED_C_FLAGS_RELEASE_SANITIZED}")
    set(ldrsp "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-rel/ldflags.rsp")
    string(REGEX REPLACE "-arch [A-Za-z0-9_]+" "" VCPKG_COMBINED_SHARED_LINKER_FLAGS_RELEASE_SANITIZED "${VCPKG_COMBINED_SHARED_LINKER_FLAGS_RELEASE}")
    file(WRITE "${ldrsp}" "${VCPKG_COMBINED_SHARED_LINKER_FLAGS_RELEASE_SANITIZED}")
    set(ENV{CFLAGS} "@${crsp}")
    if(NOT VCPKG_DETECTED_MSVC OR NOT VCPKG_TARGET_ARCHITECTURE MATCHES "^arm")
        set(ENV{ASFLAGS} "@${crsp}")
    endif()
    set(ENV{LDFLAGS} "@${ldrsp}")
    set(ENV{ARFLAGS} "${VCPKG_COMBINED_STATIC_LINKER_FLAGS_RELEASE}")

    set(BUILD_DIR         "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-rel")
    set(CONFIGURE_OPTIONS "${OPTIONS} ${OPTIONS_RELEASE}")
    set(INST_PREFIX       "${CURRENT_PACKAGES_DIR}")

    configure_file("${FFMPEG_SHARED_DIR}/build.sh.in" "${BUILD_DIR}/build.sh" @ONLY)

    z_vcpkg_setup_pkgconfig_path(CONFIG RELEASE)

    vcpkg_execute_required_process(
        COMMAND "${SHELL}" ./build.sh
        WORKING_DIRECTORY "${BUILD_DIR}"
        LOGNAME "build-${TARGET_TRIPLET}-rel"
        SAVE_LOG_FILES ffbuild/config.log
    )

    z_vcpkg_restore_pkgconfig_path()
endif()

# ========== 18. Debug build ==========

if(NOT VCPKG_BUILD_TYPE OR VCPKG_BUILD_TYPE STREQUAL "debug")
    if(VCPKG_DETECTED_MSVC)
        set(OPTIONS_DEBUG "${OPTIONS_DEBUG} --extra-ldflags=-libpath:\"${CURRENT_INSTALLED_DIR}/debug/lib\"")
    else()
        set(OPTIONS_DEBUG "${OPTIONS_DEBUG} --extra-ldflags=-L\"${CURRENT_INSTALLED_DIR}/debug/lib\"")
    endif()
    message(STATUS "Building Debug Options: ${OPTIONS_DEBUG}")
    message(STATUS "Building ${PORT} for Debug")
    file(MAKE_DIRECTORY "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-dbg")

    set(crsp "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-dbg/cflags.rsp")
    string(REGEX REPLACE "-arch [A-Za-z0-9_]+" "" VCPKG_COMBINED_C_FLAGS_DEBUG_SANITIZED "${VCPKG_COMBINED_C_FLAGS_DEBUG}")
    file(WRITE "${crsp}" "${VCPKG_COMBINED_C_FLAGS_DEBUG_SANITIZED}")
    set(ldrsp "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-dbg/ldflags.rsp")
    string(REGEX REPLACE "-arch [A-Za-z0-9_]+" "" VCPKG_COMBINED_SHARED_LINKER_FLAGS_DEBUG_SANITIZED "${VCPKG_COMBINED_SHARED_LINKER_FLAGS_DEBUG}")
    file(WRITE "${ldrsp}" "${VCPKG_COMBINED_SHARED_LINKER_FLAGS_DEBUG_SANITIZED}")
    set(ENV{CFLAGS} "@${crsp}")
    if(NOT VCPKG_DETECTED_MSVC OR NOT VCPKG_TARGET_ARCHITECTURE MATCHES "^arm")
        set(ENV{ASFLAGS} "@${crsp}")
    endif()
    set(ENV{LDFLAGS} "@${ldrsp}")
    set(ENV{ARFLAGS} "${VCPKG_COMBINED_STATIC_LINKER_FLAGS_DEBUG}")

    set(BUILD_DIR         "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-dbg")
    set(CONFIGURE_OPTIONS "${OPTIONS} ${OPTIONS_DEBUG}")
    set(INST_PREFIX       "${CURRENT_PACKAGES_DIR}/debug")

    configure_file("${FFMPEG_SHARED_DIR}/build.sh.in" "${BUILD_DIR}/build.sh" @ONLY)

    z_vcpkg_setup_pkgconfig_path(CONFIG DEBUG)

    vcpkg_execute_required_process(
        COMMAND "${SHELL}" ./build.sh
        WORKING_DIRECTORY "${BUILD_DIR}"
        LOGNAME "build-${TARGET_TRIPLET}-dbg"
        SAVE_LOG_FILES ffbuild/config.log
    )

    z_vcpkg_restore_pkgconfig_path()
endif()

# ========== 19. Windows: DEF → LIB generation ==========

if(VCPKG_TARGET_IS_WINDOWS)
    file(GLOB DEF_FILES
        "${CURRENT_PACKAGES_DIR}/lib/*.def"
        "${CURRENT_PACKAGES_DIR}/debug/lib/*.def"
    )

    if(NOT VCPKG_TARGET_IS_MINGW)
        if(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm")
            set(LIB_MACHINE_ARG /machine:ARM)
        elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm64")
            set(LIB_MACHINE_ARG /machine:ARM64)
        elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "x86")
            set(LIB_MACHINE_ARG /machine:x86)
        elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
            set(LIB_MACHINE_ARG /machine:x64)
        else()
            message(FATAL_ERROR "Unsupported target architecture")
        endif()

        foreach(DEF_FILE ${DEF_FILES})
            get_filename_component(DEF_FILE_DIR "${DEF_FILE}" DIRECTORY)
            get_filename_component(DEF_FILE_NAME "${DEF_FILE}" NAME)
            string(REGEX REPLACE "-[0-9]*\\.def" "${VCPKG_TARGET_STATIC_LIBRARY_SUFFIX}" OUT_FILE_NAME "${DEF_FILE_NAME}")
            file(TO_NATIVE_PATH "${DEF_FILE}" DEF_FILE_NATIVE)
            file(TO_NATIVE_PATH "${DEF_FILE_DIR}/${OUT_FILE_NAME}" OUT_FILE_NATIVE)
            message(STATUS "Generating ${OUT_FILE_NATIVE}")
            vcpkg_execute_required_process(
                COMMAND lib.exe "/def:${DEF_FILE_NATIVE}" "/out:${OUT_FILE_NATIVE}" ${LIB_MACHINE_ARG}
                WORKING_DIRECTORY "${CURRENT_PACKAGES_DIR}"
                LOGNAME "libconvert-${TARGET_TRIPLET}"
            )
        endforeach()
    endif()

    file(GLOB EXP_FILES
        "${CURRENT_PACKAGES_DIR}/lib/*.exp"
        "${CURRENT_PACKAGES_DIR}/debug/lib/*.exp"
    )
    file(GLOB LIB_FILES
        "${CURRENT_PACKAGES_DIR}/bin/*${VCPKG_TARGET_STATIC_LIBRARY_SUFFIX}"
        "${CURRENT_PACKAGES_DIR}/debug/bin/*${VCPKG_TARGET_STATIC_LIBRARY_SUFFIX}"
    )
    if(VCPKG_TARGET_IS_MINGW)
        file(GLOB LIB_FILES_2
            "${CURRENT_PACKAGES_DIR}/bin/*.lib"
            "${CURRENT_PACKAGES_DIR}/debug/bin/*.lib"
        )
    endif()
    set(files_to_remove ${EXP_FILES} ${LIB_FILES} ${LIB_FILES_2} ${DEF_FILES})
    if(files_to_remove)
        file(REMOVE ${files_to_remove})
    endif()
endif()

# ========== 20. Copy tools (always, except UWP) ==========

if(NOT VCPKG_TARGET_IS_UWP)
    vcpkg_copy_tools(TOOL_NAMES ffmpeg ffplay ffprobe AUTO_CLEAN)
endif()

# ========== 21. Cleanup: debug/include, debug/share, static bins ==========

file(REMOVE_RECURSE
    "${CURRENT_PACKAGES_DIR}/debug/include"
    "${CURRENT_PACKAGES_DIR}/debug/share"
)

file(REMOVE_RECURSE
    "${CURRENT_PACKAGES_DIR}/bin"
    "${CURRENT_PACKAGES_DIR}/debug/bin"
)

vcpkg_copy_pdbs()

# ========== 22. pkgconfig fixup (Windows MSVC syntax → standard) ==========

if(VCPKG_TARGET_IS_WINDOWS)
    file(GLOB pc_files
        "${CURRENT_PACKAGES_DIR}/lib/pkgconfig/*.pc"
        "${CURRENT_PACKAGES_DIR}/debug/lib/pkgconfig/*.pc"
    )
    foreach(file IN LISTS pc_files)
        file(READ "${file}" content)
        foreach(entry IN ITEMS Libs Libs.private)
            if(content MATCHES "${entry}:( [^\n]*)")
                set(old_value "${CMAKE_MATCH_1}")
                string(REGEX REPLACE "-libpath:" "-L" new_value "${old_value}")
                string(REGEX REPLACE " ([^ /]+)[.]lib" " -l\\1" new_value "${new_value}")
                string(REPLACE "${entry}:${old_value}" "${entry}:${new_value}" content "${content}")
            endif()
        endforeach()
        file(WRITE "${file}" "${content}")
    endforeach()
endif()

vcpkg_fixup_pkgconfig()

# ========== 23. Handle dependencies via pkgconfig ==========

x_vcpkg_pkgconfig_get_modules(
    PREFIX FFMPEG_PKGCONFIG
    MODULES ${FFMPEG_PKGCONFIG_MODULES}
    LIBS
)

function(append_dependencies_from_libs out)
    cmake_parse_arguments(PARSE_ARGV 1 "arg" "" "LIBS" "")
    separate_arguments(contents UNIX_COMMAND "${arg_LIBS}")
    list(FILTER contents EXCLUDE REGEX "^-F.+")
    list(FILTER contents EXCLUDE REGEX "^-framework$")
    list(FILTER contents EXCLUDE REGEX "^-L.+")
    list(FILTER contents EXCLUDE REGEX "^-libpath:.+")
    list(TRANSFORM contents REPLACE "^-Wl,-framework," "-l")
    list(FILTER contents EXCLUDE REGEX "^-Wl,.+")
    list(TRANSFORM contents REPLACE "^-l" "")
    list(FILTER contents EXCLUDE REGEX "^avutil$")
    list(FILTER contents EXCLUDE REGEX "^avcodec$")
    list(FILTER contents EXCLUDE REGEX "^avdevice$")
    list(FILTER contents EXCLUDE REGEX "^avfilter$")
    list(FILTER contents EXCLUDE REGEX "^avformat$")
    list(FILTER contents EXCLUDE REGEX "^swresample$")
    list(FILTER contents EXCLUDE REGEX "^swscale$")
    if(VCPKG_TARGET_IS_WINDOWS)
        list(TRANSFORM contents TOLOWER)
    endif()
    if(contents)
        list(APPEND "${out}" "${contents}")
        set("${out}" "${${out}}" PARENT_SCOPE)
    endif()
endfunction()

append_dependencies_from_libs(FFMPEG_DEPENDENCIES_RELEASE LIBS "${FFMPEG_PKGCONFIG_LIBS_RELEASE}")
append_dependencies_from_libs(FFMPEG_DEPENDENCIES_DEBUG   LIBS "${FFMPEG_PKGCONFIG_LIBS_DEBUG}")

list(REVERSE FFMPEG_DEPENDENCIES_RELEASE)
list(REVERSE FFMPEG_DEPENDENCIES_DEBUG)
list(REMOVE_DUPLICATES FFMPEG_DEPENDENCIES_RELEASE)
list(REMOVE_DUPLICATES FFMPEG_DEPENDENCIES_DEBUG)
list(REVERSE FFMPEG_DEPENDENCIES_RELEASE)
list(REVERSE FFMPEG_DEPENDENCIES_DEBUG)

message(STATUS "Dependencies (release): ${FFMPEG_DEPENDENCIES_RELEASE}")
message(STATUS "Dependencies (debug):   ${FFMPEG_DEPENDENCIES_DEBUG}")

# ========== 24. Version extraction ==========

function(extract_regex_from_file out)
    cmake_parse_arguments(PARSE_ARGV 1 "arg" "MAJOR" "FILE_WITHOUT_EXTENSION;REGEX" "")
    file(READ "${arg_FILE_WITHOUT_EXTENSION}.h" contents)
    if(contents MATCHES "${arg_REGEX}")
        if(NOT CMAKE_MATCH_COUNT EQUAL 1)
            message(FATAL_ERROR "Could not identify match group in regular expression \"${arg_REGEX}\"")
        endif()
    else()
        if(arg_MAJOR)
            file(READ "${arg_FILE_WITHOUT_EXTENSION}_major.h" contents)
            if(contents MATCHES "${arg_REGEX}")
                if(NOT CMAKE_MATCH_COUNT EQUAL 1)
                    message(FATAL_ERROR "Could not identify match group in regular expression \"${arg_REGEX}\"")
                endif()
            else()
                message(WARNING "Could not find line matching \"${arg_REGEX}\" in file \"${arg_FILE_WITHOUT_EXTENSION}_major.h\"")
            endif()
        else()
            message(WARNING "Could not find line matching \"${arg_REGEX}\" in file \"${arg_FILE_WITHOUT_EXTENSION}.h\"")
        endif()
    endif()
    set("${out}" "${CMAKE_MATCH_1}" PARENT_SCOPE)
endfunction()

function(extract_version_from_component out)
    cmake_parse_arguments(PARSE_ARGV 1 "arg" "" "COMPONENT" "")
    string(TOLOWER "${arg_COMPONENT}" component_lower)
    string(TOUPPER "${arg_COMPONENT}" component_upper)
    extract_regex_from_file(major_version
        FILE_WITHOUT_EXTENSION "${SOURCE_PATH}/${component_lower}/version"
        MAJOR
        REGEX "#define ${component_upper}_VERSION_MAJOR[ ]+([0-9]+)"
    )
    extract_regex_from_file(minor_version
        FILE_WITHOUT_EXTENSION "${SOURCE_PATH}/${component_lower}/version"
        REGEX "#define ${component_upper}_VERSION_MINOR[ ]+([0-9]+)"
    )
    extract_regex_from_file(micro_version
        FILE_WITHOUT_EXTENSION "${SOURCE_PATH}/${component_lower}/version"
        REGEX "#define ${component_upper}_VERSION_MICRO[ ]+([0-9]+)"
    )
    set("${out}" "${major_version}.${minor_version}.${micro_version}" PARENT_SCOPE)
endfunction()

extract_regex_from_file(FFMPEG_VERSION_FULL
    FILE_WITHOUT_EXTENSION "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-rel/libavutil/ffversion"
    REGEX "#define FFMPEG_VERSION[ ]+\"(.+)\""
)

extract_version_from_component(LIBAVUTIL_VERSION   COMPONENT libavutil)
extract_version_from_component(LIBAVCODEC_VERSION  COMPONENT libavcodec)
extract_version_from_component(LIBAVDEVICE_VERSION COMPONENT libavdevice)
extract_version_from_component(LIBAVFILTER_VERSION COMPONENT libavfilter)
extract_version_from_component(LIBAVFORMAT_VERSION COMPONENT libavformat)
extract_version_from_component(LIBSWRESAMPLE_VERSION COMPONENT libswresample)
extract_version_from_component(LIBSWSCALE_VERSION  COMPONENT libswscale)

# ========== 25. Copyright handling ==========

file(STRINGS
    "${CURRENT_BUILDTREES_DIR}/build-${TARGET_TRIPLET}-rel-out.log"
    LICENSE_STRING
    REGEX "License: .*"
    LIMIT_COUNT 1
)

if(LICENSE_STRING STREQUAL "License: LGPL version 2.1 or later")
    set(LICENSE_FILE "COPYING.LGPLv2.1")
elseif(LICENSE_STRING STREQUAL "License: LGPL version 3 or later")
    set(LICENSE_FILE "COPYING.LGPLv3")
elseif(LICENSE_STRING STREQUAL "License: GPL version 2 or later")
    set(LICENSE_FILE "COPYING.GPLv2")
elseif(LICENSE_STRING STREQUAL "License: GPL version 3 or later")
    set(LICENSE_FILE "COPYING.GPLv3")
elseif(LICENSE_STRING STREQUAL "License: nonfree and unredistributable")
    set(LICENSE_FILE "COPYING.NONFREE")
    file(WRITE "${SOURCE_PATH}/${LICENSE_FILE}" "${LICENSE_STRING}")
else()
    message(FATAL_ERROR "Failed to identify license (${LICENSE_STRING})")
endif()

# ========== 26. FindFFMPEG.cmake + usage generation ==========

configure_file(
    "${FFMPEG_SHARED_DIR}/FindFFMPEG.cmake.in"
    "${CURRENT_PACKAGES_DIR}/share/${PORT}/FindFFMPEG.cmake"
    @ONLY
)

configure_file(
    "${FFMPEG_SHARED_DIR}/vcpkg-cmake-wrapper.cmake"
    "${CURRENT_PACKAGES_DIR}/share/${PORT}/vcpkg-cmake-wrapper.cmake"
    @ONLY
)

file(INSTALL
    "${CURRENT_PORT_DIR}/usage"
    DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"
)

if("static" IN_LIST FEATURES
   AND NOT VCPKG_TARGET_IS_WINDOWS
   AND NOT VCPKG_TARGET_IS_OSX
   AND NOT VCPKG_TARGET_IS_IOS)
    file(APPEND "${CURRENT_PACKAGES_DIR}/share/${PORT}/usage" "
To use the static libraries to build your own shared library,
you may need to add the following link option for your library:

  -Wl,-Bsymbolic
")
endif()

# ========== 27. Install copyright ==========

vcpkg_install_copyright(FILE_LIST "${SOURCE_PATH}/${LICENSE_FILE}")
