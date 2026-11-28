# ffmpeg-builder.cmake
#
# Shared CMake build base class for FFmpeg vcpkg ports.
#
# Per-version portfile.cmake must set these variables before include():
#   FFMPEG_VERSION   - FFmpeg upstream version string (e.g. "8.1.1")
#   FFMPEG_SHA512    - Source tarball SHA512 checksum
#   FFMPEG_PATCHES   - List of patch file names (relative to port directory)
#   FFMPEG_PATCHES_DIR - Patches directory (optional, defaults to builder dir)
#   FFMPEG_REF       - Git ref for checkout (optional, defaults to "n${FFMPEG_VERSION}")
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
# FindFFmpeg.cmake generation, and copyright.

if("static" IN_LIST FEATURES)
    set(VCPKG_LIBRARY_LINKAGE static)
else()
    set(VCPKG_LIBRARY_LINKAGE dynamic)
endif()

set(FFMPEG_SHARED_DIR ${CMAKE_CURRENT_LIST_DIR})

# ---- Guard ----
if(DEFINED __FFMPEG_PORT_BASE_INCLUDED)
    return()
endif()
set(__FFMPEG_PORT_BASE_INCLUDED TRUE)

# The installed Port and metadata contract is a paired Release/Debug SDK.
# Fail before acquiring or compiling sources for unsupported single-config
# triplets. Release-only public ZIPs are produced later by the packager.
if(VCPKG_BUILD_TYPE)
    message(FATAL_ERROR "FFmpeg Port requires both Release and Debug configurations (VCPKG_BUILD_TYPE must be unset)")
endif()

# Enforce feature/explicit-license constraints even for direct vcpkg install.
include("${CMAKE_CURRENT_LIST_DIR}/../constraints.cmake")

# ---- Macros: feature → flag mapping ----
# ffmpeg_feature(name "--flag1" "--flag2" ...)
#   If feature "name" is in FEATURES list, append all given flags to OPTIONS.
macro(ffmpeg_feature _name)
    if("${_name}" IN_LIST FEATURES)
        foreach(_f ${ARGN})
            set(OPTIONS "${OPTIONS} ${_f}")
            string(TOUPPER "${_name}" _uc)
            set(ENABLE_${_uc} ON)
            # Verify every explicit feature switch, including features
            # which expand to several enable flags. Core libraries are
            # checked through installed modules and licenses separately.
            separate_arguments(_ff_feature_args UNIX_COMMAND "${_f}")
            foreach(_ff_arg IN LISTS _ff_feature_args)
                if(_ff_arg MATCHES "^--enable-([a-zA-Z0-9_-]+)$")
                    set(_ff_feature_switch "${CMAKE_MATCH_1}")
                    if(NOT _ff_feature_switch MATCHES "^(gpl|nonfree)$")
                        string(REPLACE "-" "_" _ff_feature_macro "${_ff_feature_switch}")
                        string(TOUPPER "${_ff_feature_macro}" _ff_feature_macro)
                        list(APPEND _ff_requested_feature_macros "${_ff_feature_macro}")
                    endif()
                endif()
            endforeach()
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
foreach(_required_var FFMPEG_VERSION FFMPEG_SHA512 CURRENT_PORT_DIR)
    if(NOT DEFINED ${_required_var})
        message(FATAL_ERROR "ffmpeg-builder.cmake: required variable ${_required_var} is not set. "
                            "Set it before include().")
    endif()
endforeach()

if(NOT DEFINED FFMPEG_PATCHES_DIR)
    set(FFMPEG_PATCHES_DIR "${CMAKE_CURRENT_LIST_DIR}")
endif()

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

if(DEFINED FFMPEG_REF)
    set(_FFMPEG_REF "${FFMPEG_REF}")
else()
    set(_FFMPEG_REF "n${FFMPEG_VERSION}")
endif()

vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO ffmpeg/ffmpeg
    REF "${_FFMPEG_REF}"
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

# ffmpeg-opstool ops_asmgen path: host-compiled code generator for swscale
if(DEFINED FFMPEG_NEED_OPSTOOL AND FFMPEG_NEED_OPSTOOL)
    vcpkg_add_to_path(PREPEND "${CURRENT_HOST_INSTALLED_DIR}/manual-tools/ffmpeg-opstool")
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

if(VCPKG_LIBRARY_LINKAGE STREQUAL "static")
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

# Preserve the vcpkg helper's executable/PATH handling and its native path
# separator. Isolate the search only for the MSVC target, not other platforms.
macro(ffmpeg_setup_native_pkgconfig _config)
    if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
        foreach(_envvar PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR)
            if(DEFINED ENV{${_envvar}})
                set(_ff_saved_env_${_envvar} "$ENV{${_envvar}}")
            else()
                unset(_ff_saved_env_${_envvar})
            endif()
            unset(ENV{${_envvar}})
        endforeach()
    endif()
    if(VCPKG_DETECTED_MSVC)
        if(DEFINED ENV{LIB})
            set(_ff_saved_native_lib "$ENV{LIB}")
        else()
            unset(_ff_saved_native_lib)
        endif()
        if("${_config}" STREQUAL "DEBUG")
            set(_ff_config_lib "${CURRENT_INSTALLED_DIR}/debug/lib")
        else()
            set(_ff_config_lib "${CURRENT_INSTALLED_DIR}/lib")
        endif()
        # MSVC /LIBPATH takes precedence over LIB. The default installed
        # directory is a fallback; explicit .pc search order must win.
        vcpkg_host_path_list(PREPEND ENV{LIB} "${_ff_config_lib}")
    endif()
    z_vcpkg_setup_pkgconfig_path(CONFIG ${_config})
    if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
        set(ENV{PKG_CONFIG_LIBDIR} "$ENV{PKG_CONFIG_PATH}")
    endif()
endmacro()

macro(ffmpeg_restore_native_pkgconfig)
    z_vcpkg_restore_pkgconfig_path()
    if(VCPKG_DETECTED_MSVC)
        if(DEFINED _ff_saved_native_lib)
            set(ENV{LIB} "${_ff_saved_native_lib}")
        else()
            unset(ENV{LIB})
        endif()
    endif()
    if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
        foreach(_envvar PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR)
            if(DEFINED _ff_saved_env_${_envvar})
                set(ENV{${_envvar}} "${_ff_saved_env_${_envvar}}")
            else()
                unset(ENV{${_envvar}})
            endif()
        endforeach()
    endif()
endmacro()

# ========== 17. Release build ==========

if(NOT VCPKG_BUILD_TYPE OR VCPKG_BUILD_TYPE STREQUAL "release")
    if(NOT VCPKG_DETECTED_MSVC)
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

    ffmpeg_setup_native_pkgconfig(RELEASE)

    vcpkg_execute_required_process(
        COMMAND "${SHELL}" ./build.sh
        WORKING_DIRECTORY "${BUILD_DIR}"
        LOGNAME "build-${TARGET_TRIPLET}-rel"
        SAVE_LOG_FILES ffbuild/config.log
    )

    ffmpeg_restore_native_pkgconfig()
endif()

# ========== 18. Debug build ==========

if(NOT VCPKG_BUILD_TYPE OR VCPKG_BUILD_TYPE STREQUAL "debug")
    if(NOT VCPKG_DETECTED_MSVC)
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

    ffmpeg_setup_native_pkgconfig(DEBUG)

    vcpkg_execute_required_process(
        COMMAND "${SHELL}" ./build.sh
        WORKING_DIRECTORY "${BUILD_DIR}"
        LOGNAME "build-${TARGET_TRIPLET}-dbg"
        SAVE_LOG_FILES ffbuild/config.log
    )

    ffmpeg_restore_native_pkgconfig()
endif()

# Verify actual Configure results for the requested feature switches.
# FFmpeg emits CONFIG_* for library, hardware and program options. Its
# thread switches use HAVE_*; SDL2 used HAVE_SDL2 on older releases.
# Prefer CONFIG_SDL2 when present rather than masking an explicit zero.
list(REMOVE_DUPLICATES _ff_requested_feature_macros)
foreach(_cfg rel dbg)
    set(_ff_config_text "")
    foreach(_header config.h config_components.h)
        set(_ff_config_file "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-${_cfg}/${_header}")
        if(EXISTS "${_ff_config_file}")
            file(READ "${_ff_config_file}" _ff_config_part)
            string(APPEND _ff_config_text "\n${_ff_config_part}")
        endif()
    endforeach()
    foreach(_feature IN LISTS _ff_requested_feature_macros)
        set(_macro "CONFIG_${_feature}")
        if(_feature MATCHES "^(PTHREADS|W32THREADS)$")
            set(_macro "HAVE_${_feature}")
        elseif(_feature STREQUAL "SDL2" AND NOT _ff_config_text MATCHES "(^|\n)#[ \t]*define[ \t]+CONFIG_SDL2[ \t]+")
            set(_macro HAVE_SDL2)
        endif()
        if(NOT _ff_config_text MATCHES "(^|\n)#[ \t]*define[ \t]+${_macro}[ \t]+1([ \t\r\n]|$)")
            message(FATAL_ERROR "FFmpeg ${_cfg}: requested feature not enabled (${_macro})")
        endif()
    endforeach()
endforeach()

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

set(FFMPEG_TOOLS_TO_COPY "")

foreach(tool IN ITEMS ffmpeg ffprobe ffplay)
    if(tool IN_LIST FEATURES)
        list(APPEND FFMPEG_TOOLS_TO_COPY ${tool})
    endif()
endforeach()

if(FFMPEG_TOOLS_TO_COPY)
    vcpkg_copy_tools(
        TOOL_NAMES ${FFMPEG_TOOLS_TO_COPY}
        DESTINATION "${CURRENT_PACKAGES_DIR}/tools/ffmpeg"
        AUTO_CLEAN
    )
endif()


file(REMOVE_RECURSE 
    "${CURRENT_PACKAGES_DIR}/debug/include"
    "${CURRENT_PACKAGES_DIR}/debug/share")

if(VCPKG_LIBRARY_LINKAGE STREQUAL "static")
    file(REMOVE_RECURSE "${CURRENT_PACKAGES_DIR}/bin"
    "${CURRENT_PACKAGES_DIR}/debug/bin")
endif()

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

# BEGIN native pkg-config path normalization
# Native Windows pkgconf escapes spaces when expanding path variables.
# Quoting a variable-only path flag causes a second escape, which breaks
# shell tokenization and CMake FindPkgConfig. Only unwrap these exact tokens;
# leave literal paths, definitions and other quoted flags untouched.
if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
    file(GLOB _ff_path_pc_files
        "${CURRENT_PACKAGES_DIR}/lib/pkgconfig/lib*.pc"
        "${CURRENT_PACKAGES_DIR}/debug/lib/pkgconfig/lib*.pc")
    foreach(_ff_path_pc IN LISTS _ff_path_pc_files)
        file(READ "${_ff_path_pc}" _ff_path_text)
        string(REGEX REPLACE [[\"(-[LI]\$\{[a-zA-Z_][a-zA-Z0-9_]*\}(/[a-zA-Z0-9_./+-]+)?)\"]]
            [[\1]] _ff_path_text "${_ff_path_text}")
        file(WRITE "${_ff_path_pc}" "${_ff_path_text}")
    endforeach()
endif()
# END native pkg-config path normalization

# A shared FFmpeg DLL already links its private dependencies. Do not expose
# their static archives through the public import-library SDK. Keep the
# internal module graph, public Requires, Libs and Cflags intact.
# The native static Port still needs its full private dependency metadata.
# BEGIN shared pkg-config normalization
if(VCPKG_LIBRARY_LINKAGE STREQUAL "dynamic")
    foreach(_ff_pc_dir "${CURRENT_PACKAGES_DIR}/lib/pkgconfig" "${CURRENT_PACKAGES_DIR}/debug/lib/pkgconfig")
        file(GLOB shared_pc_files "${_ff_pc_dir}/*.pc")
        # Preserve known FFmpeg module references even if the corresponding
        # .pc is missing; the downstream graph validation must reject that.
        set(_ff_internal_packages libavutil libavcodec libavformat libavdevice
            libavfilter libswscale libswresample libavresample libpostproc)
        foreach(pc_file IN LISTS shared_pc_files)
            get_filename_component(_ff_pc_name "${pc_file}" NAME_WE)
            list(APPEND _ff_internal_packages "${_ff_pc_name}")
        endforeach()
        foreach(pc_file IN LISTS shared_pc_files)
            file(READ "${pc_file}" pc_content)
            string(REGEX REPLACE "[ \t]*\\\\\n[ \t]*" " " pc_content "${pc_content}")
            string(REGEX REPLACE "(^|\n)Libs[.]private:[^\n]*" "\\1Libs.private:" pc_content "${pc_content}")
            # Cflags.private is only needed when consuming a static archive.
            string(REGEX REPLACE "(^|\n)Cflags[.]private:[^\n]*" "\\1Cflags.private:" pc_content "${pc_content}")
            # Preserve versioned edges between installed FFmpeg modules.
            # Private third-party packages have already been linked into
            # the DLL in this project's static-dependency build.
            if(pc_content MATCHES "(^|\n)Requires[.]private:[ \t]*([^\n]*)")
                set(_ff_old_requires "${CMAKE_MATCH_0}")
                set(_ff_leading "${CMAKE_MATCH_1}")
                set(_ff_raw_requires "${CMAKE_MATCH_2}")
                string(REGEX MATCHALL "[^ \t,<>!=]+([ \t]*[<>=!]+[ \t]*[^ \t,]+)?" _ff_requirements "${_ff_raw_requires}")
                set(_ff_kept "")
                foreach(_ff_requirement IN LISTS _ff_requirements)
                    string(REGEX MATCH "^[^ \t,<>!=]+" _ff_pc_name "${_ff_requirement}")
                    if(_ff_pc_name IN_LIST _ff_internal_packages)
                        list(APPEND _ff_kept "${_ff_requirement}")
                    endif()
                endforeach()
                list(JOIN _ff_kept ", " _ff_kept)
                if(_ff_kept)
                    set(_ff_kept " ${_ff_kept}")
                endif()
                string(REPLACE "${_ff_old_requires}" "${_ff_leading}Requires.private:${_ff_kept}" pc_content "${pc_content}")
            endif()
            file(WRITE "${pc_file}" "${pc_content}")
        endforeach()
    endforeach()
endif()
# END shared pkg-config normalization

# ========== 23. Handle dependencies via pkgconfig ==========
#
# Per-module dependency resolution:
#   1. Query normalized vcpkg .pc files for module edges and --libs
#      (vcpkg_fixup_pkgconfig folds private fields into static public fields).
#   2. Separate internal FFmpeg deps from external system deps
#   3. Topological sort modules by internal deps
#   4. Remove transitive external deps (each module keeps only its direct deps)
#   5. Generate template variables for FindFFmpeg.cmake

# The requested modules must exist; discover additional modules emitted by
# upstream (including postproc and avresample on historical releases).
# BEGIN module dependency metadata
set(_ff_requested_modules "${FFMPEG_PKGCONFIG_MODULES}")
file(GLOB _ff_release_pc RELATIVE "${CURRENT_PACKAGES_DIR}/lib/pkgconfig"
    "${CURRENT_PACKAGES_DIR}/lib/pkgconfig/lib*.pc")
set(FFMPEG_PKGCONFIG_MODULES "")
foreach(_pc IN LISTS _ff_release_pc)
    string(REGEX REPLACE "[.]pc$" "" _pkg "${_pc}")
    if(NOT _pkg MATCHES "^lib[a-z0-9_]+$")
        message(FATAL_ERROR "Unexpected FFmpeg pkg-config module: ${_pkg}")
    endif()
    if(NOT EXISTS "${CURRENT_PACKAGES_DIR}/debug/lib/pkgconfig/${_pc}")
        message(FATAL_ERROR "Missing Debug pkg-config module: ${_pkg}")
    endif()
    list(APPEND FFMPEG_PKGCONFIG_MODULES "${_pkg}")
endforeach()
foreach(_pkg IN LISTS _ff_requested_modules)
    if(NOT _pkg IN_LIST FFMPEG_PKGCONFIG_MODULES)
        message(FATAL_ERROR "Requested FFmpeg module missing: ${_pkg}")
    endif()
endforeach()
file(GLOB _ff_debug_pc RELATIVE "${CURRENT_PACKAGES_DIR}/debug/lib/pkgconfig"
    "${CURRENT_PACKAGES_DIR}/debug/lib/pkgconfig/lib*.pc")
if(NOT "${_ff_release_pc}" STREQUAL "${_ff_debug_pc}")
    message(FATAL_ERROR "Release/Debug FFmpeg module sets differ")
endif()
set(FFMPEG_CORE_SHORT_NAMES "")
foreach(_pkg IN LISTS FFMPEG_PKGCONFIG_MODULES)
    string(REGEX REPLACE "^lib" "" _name "${_pkg}")
    list(APPEND FFMPEG_CORE_SHORT_NAMES "${_name}")
endforeach()

find_program(PKGCONF pkgconf
    PATHS "${CURRENT_HOST_INSTALLED_DIR}/tools/pkgconf" NO_DEFAULT_PATH)

# Wrapper: isolated per-invocation pkgconf search environment.
function(ffmpeg_pkgconf_run out_var config)
    if(config STREQUAL "DEBUG")
        set(_ff_prefix "debug/")
    elseif(config STREQUAL "RELEASE")
        set(_ff_prefix "")
    else()
        message(FATAL_ERROR "Unknown pkg-config build configuration: ${config}")
    endif()
    # Mirror vcpkg's per-configuration library/share search order. For
    # MSVC package metadata, exclude unrelated host/system .pc directories.
    set(_ff_paths "${CURRENT_PACKAGES_DIR}/${_ff_prefix}lib/pkgconfig")
    string(APPEND _ff_paths "${VCPKG_HOST_PATH_SEPARATOR}${CURRENT_PACKAGES_DIR}/share/pkgconfig")
    string(APPEND _ff_paths "${VCPKG_HOST_PATH_SEPARATOR}${CURRENT_INSTALLED_DIR}/${_ff_prefix}lib/pkgconfig")
    string(APPEND _ff_paths "${VCPKG_HOST_PATH_SEPARATOR}${CURRENT_INSTALLED_DIR}/share/pkgconfig")
    set(_ff_env "PKG_CONFIG_PATH=${_ff_paths}")
    if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
        # Use explicit environment arguments, not a persistent global change.
        execute_process(
            COMMAND "${CMAKE_COMMAND}" -E env --unset=PKG_CONFIG_SYSROOT_DIR "${_ff_env}"
                "PKG_CONFIG_LIBDIR=${_ff_paths}" "${PKGCONF}" ${ARGN}
            OUTPUT_VARIABLE _ff_result
            OUTPUT_STRIP_TRAILING_WHITESPACE
            COMMAND_ERROR_IS_FATAL ANY
        )
    else()
        execute_process(
            COMMAND "${CMAKE_COMMAND}" -E env "${_ff_env}" "${PKGCONF}" ${ARGN}
            OUTPUT_VARIABLE _ff_result
            OUTPUT_STRIP_TRAILING_WHITESPACE
            COMMAND_ERROR_IS_FATAL ANY
        )
    endif()
    set("${out_var}" "${_ff_result}" PARENT_SCOPE)
endfunction()

# 1a. Derive internal module graph independently in both configurations.
function(ffmpeg_module_deps out pkgmod config)
    string(REGEX REPLACE "^lib" "" short_name "${pkgmod}")
    set(deps "")
    foreach(query --print-requires --print-requires-private)
        ffmpeg_pkgconf_run(deps_raw "${config}" "${pkgmod}" "${query}")
        string(REPLACE "\n" ";" lines "${deps_raw}")
        foreach(line IN LISTS lines)
            string(STRIP "${line}" line)
            if(NOT line STREQUAL "")
                string(REGEX REPLACE "^([^ \t]+).*$" "\\1" name "${line}")
                string(REGEX REPLACE "^lib" "" name "${name}")
                if(name IN_LIST FFMPEG_CORE_SHORT_NAMES AND NOT name STREQUAL short_name)
                    list(APPEND deps "${name}")
                endif()
            endif()
        endforeach()
    endforeach()
    list(REMOVE_DUPLICATES deps)
    list(SORT deps)
    set("${out}" "${deps}" PARENT_SCOPE)
endfunction()
foreach(pkgmod IN LISTS FFMPEG_PKGCONFIG_MODULES)
    string(REGEX REPLACE "^lib" "" short_name "${pkgmod}")
    ffmpeg_module_deps(FFMPEG_${short_name}_DEPS "${pkgmod}" RELEASE)
    ffmpeg_module_deps(_debug_deps "${pkgmod}" DEBUG)
    if(NOT "${FFMPEG_${short_name}_DEPS}" STREQUAL "${_debug_deps}")
        message(FATAL_ERROR "Release/Debug internal module graph differs: ${pkgmod}")
    endif()
endforeach()

# 1b. LIBRARIES via pkgconf --libs
foreach(pkgmod IN LISTS FFMPEG_PKGCONFIG_MODULES)
    string(REGEX REPLACE "^lib" "" short_name "${pkgmod}")
    foreach(cfg RELEASE DEBUG)
        ffmpeg_pkgconf_run(libs_raw "${cfg}" --libs "${pkgmod}")
        set(PKG_${pkgmod}_LIBS_${cfg} "${libs_raw}")
    endforeach()
endforeach()

set(_ff_installed_archives "")
if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
    get_filename_component(_ff_triplet "${CURRENT_INSTALLED_DIR}" NAME)
    file(GLOB _ff_lists "${CURRENT_INSTALLED_DIR}/../vcpkg/info/*_${_ff_triplet}.list")
    foreach(_ff_list IN LISTS _ff_lists)
        file(STRINGS "${_ff_list}" _ff_files
            REGEX "^${_ff_triplet}/(debug/)?lib/.+[.][Ll][Ii][Bb]$")
        foreach(_ff_file IN LISTS _ff_files)
            string(REGEX REPLACE "^${_ff_triplet}/" "" _ff_file "${_ff_file}")
            string(TOLOWER "${_ff_file}" _ff_file)
            list(APPEND _ff_installed_archives "${_ff_file}")
        endforeach()
    endforeach()
    list(REMOVE_DUPLICATES _ff_installed_archives)
endif()


# Compare normalized paths case-insensitively for Windows, but preserve the
# spelling of the actual filename and all non-path linker arguments.
function(ffmpeg_relative_to out path base)
    cmake_path(NORMAL_PATH path)
    cmake_path(NORMAL_PATH base)
    if(CMAKE_HOST_WIN32)
        string(TOLOWER "${path}" path)
        string(TOLOWER "${base}" base)
    endif()
    cmake_path(IS_PREFIX base "${path}" NORMALIZE inside)
    if(inside)
        cmake_path(RELATIVE_PATH path BASE_DIRECTORY "${base}" OUTPUT_VARIABLE relative)
        set("${out}" "${relative}" PARENT_SCOPE)
    else()
        set("${out}" "" PARENT_SCOPE)
    endif()
endfunction()

function(ffmpeg_classify_library out name config)
    if(NOT VCPKG_TARGET_IS_WINDOWS OR VCPKG_TARGET_IS_MINGW)
        set("${out}" "${name}" PARENT_SCOPE)
        return()
    endif()
    if(config STREQUAL "DEBUG")
        set(prefix "debug/")
        set(other "")
    else()
        set(prefix "")
        set(other "debug/")
    endif()
    set(_config_root "${CURRENT_INSTALLED_DIR}/${prefix}lib")
    set(_opposite_root "${CURRENT_INSTALLED_DIR}/${other}lib")
    cmake_path(CONVERT "$ENV{LIB}" TO_CMAKE_PATH_LIST _toolchain_dirs NORMALIZE)
    if(IS_ABSOLUTE "${name}")
        ffmpeg_relative_to(_relative "${name}" "${_config_root}")
        if(_relative AND EXISTS "${name}" AND NOT IS_DIRECTORY "${name}")
            set("${out}" "vcpkg-lib:${_relative}" PARENT_SCOPE)
            return()
        endif()
        ffmpeg_relative_to(_relative "${name}" "${_opposite_root}")
        if(_relative)
            message(FATAL_ERROR "${config} dependency ${name} belongs to the opposite configuration")
        endif()
        foreach(dir IN LISTS _toolchain_dirs)
            ffmpeg_relative_to(_relative "${name}" "${dir}")
            if(_relative AND NOT _relative MATCHES "/" AND EXISTS "${name}")
                set("${out}" "${_relative}" PARENT_SCOPE)
                return()
            endif()
        endforeach()
        message(FATAL_ERROR "${config} dependency ${name} is missing or an external absolute library, not relocatable")
    endif()
    set(candidates "${name}")
    if(name MATCHES "^:")
        string(SUBSTRING "${name}" 1 -1 candidates)
    elseif(NOT name MATCHES "[.][Ll][Ii][Bb]$")
        set(candidates "${name}.lib;lib${name}.lib")
    endif()
    # Preserve the effective pkg-config search order. Search directories
    # apply to the whole link line; a manual-link archive is usable only
    # when the metadata explicitly selects its directory.
    set(_dirs ${ARGN} "${_config_root}")
    list(REMOVE_DUPLICATES _dirs)
    foreach(dir IN LISTS _dirs)
        foreach(candidate IN LISTS candidates)
            if(EXISTS "${dir}/${candidate}" AND NOT IS_DIRECTORY "${dir}/${candidate}")
                ffmpeg_relative_to(_relative "${dir}/${candidate}" "${_config_root}")
                if(_relative)
                    set("${out}" "vcpkg-lib:${_relative}" PARENT_SCOPE)
                    return()
                endif()
                # A module's own archive is filtered earlier; no other
                # package-build paths may escape into the installed SDK.
                ffmpeg_relative_to(_relative "${dir}/${candidate}" "${_opposite_root}")
                if(_relative)
                    message(FATAL_ERROR "${config} dependency ${name} selects the opposite configuration search directory")
                endif()
                foreach(_toolchain_dir IN LISTS _toolchain_dirs)
                    ffmpeg_relative_to(_relative "${dir}/${candidate}" "${_toolchain_dir}")
                    if(_relative AND NOT _relative MATCHES "/")
                        set("${out}" "${name}" PARENT_SCOPE)
                        return()
                    endif()
                endforeach()
                message(FATAL_ERROR "${config} dependency ${name} selects an external library: ${dir}")
            endif()
            ffmpeg_relative_to(_relative "${dir}/${candidate}" "${_config_root}")
            if(_relative)
                string(TOLOWER "${prefix}lib/${_relative}" _record)
                if(_record IN_LIST _ff_installed_archives)
                    message(FATAL_ERROR "${config} dependency ${name} is recorded by vcpkg but its archive is missing")
                endif()
            endif()
        endforeach()
    endforeach()
    foreach(candidate IN LISTS candidates)
        string(TOLOWER "${other}lib/${candidate}" _record)
        if(EXISTS "${_opposite_root}/${candidate}" OR _record IN_LIST _ff_installed_archives)
            message(FATAL_ERROR "${config} dependency ${name} exists only in the opposite configuration")
        endif()
        foreach(dir IN LISTS _toolchain_dirs)
            if(EXISTS "${dir}/${candidate}" AND NOT IS_DIRECTORY "${dir}/${candidate}")
                # Retain the portable linker name, never the SDK's
                # machine-local absolute path.
                set("${out}" "${name}" PARENT_SCOPE)
                return()
            endif()
        endforeach()
    endforeach()
    message(FATAL_ERROR "${config} dependency library ${name} not found in the installed configuration or MSVC LIB search path")
endfunction()

# 2. Parse normalized --libs: strip build-root flags, filter out internal modules
foreach(pkgmod IN LISTS FFMPEG_PKGCONFIG_MODULES)
    string(REGEX REPLACE "^lib" "" short_name "${pkgmod}")
    set(_skip_list ${FFMPEG_CORE_SHORT_NAMES})
    set(_closure "")
    set(_pending ${FFMPEG_${short_name}_DEPS})
    while(_pending)
        list(POP_FRONT _pending _dep)
        if(NOT _dep IN_LIST _closure)
            list(APPEND _closure "${_dep}")
            list(APPEND _pending ${FFMPEG_${_dep}_DEPS})
        endif()
    endwhile()
    foreach(cfg RELEASE DEBUG)
        set(libs_str "${PKG_${pkgmod}_LIBS_${cfg}}")
        # Installed third-party .pc files may still contain the quotes
        # introduced by vcpkg. Decode pkgconf's extra space escape before
        # interpreting the library search order; do not mutate dependencies.
        if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
            # pkgconf versions can escape quoted variable paths twice or
            # three times. Normalize only the escaped whitespace sequence.
            while(libs_str MATCHES [[\\ ]])
                string(REPLACE [[\\ ]] [[\ ]] libs_str "${libs_str}")
            endwhile()
        endif()
        separate_arguments(libs UNIX_COMMAND "${libs_str}")
        set(external "")
        if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
            set(_search_dirs "")
            set(_expect_dir FALSE)
            foreach(_token IN LISTS libs)
                if(_expect_dir)
                    list(APPEND _search_dirs "${_token}")
                    set(_expect_dir FALSE)
                elseif(_token STREQUAL "-L")
                    set(_expect_dir TRUE)
                elseif(_token MATCHES "^(-L|-libpath:|/LIBPATH:)(.+)$")
                    list(APPEND _search_dirs "${CMAKE_MATCH_2}")
                endif()
            endforeach()
            set(_expect_dir FALSE)
            foreach(lib IN LISTS libs)
                if(_expect_dir)
                    set(_expect_dir FALSE)
                    continue()
                elseif(lib STREQUAL "-L")
                    set(_expect_dir TRUE)
                    continue()
                elseif(lib MATCHES "^(-L|-libpath:|/LIBPATH:).+")
                    continue()
                endif()
                if(lib MATCHES "^-Wl,(.+)$")
                    # MSVC linker options are not archive names. Preserve
                    # case and pass '-' options via the legacy link list too.
                    string(REPLACE "," ";" _options "${CMAKE_MATCH_1}")
                    foreach(_option IN LISTS _options)
                        if(_option MATCHES "^/(.+)$")
                            set(_option "-${CMAKE_MATCH_1}")
                        endif()
                        list(APPEND external "${_option}")
                    endforeach()
                    continue()
                elseif(lib MATCHES "^/[A-Za-z][A-Za-z0-9_-]*:" AND NOT IS_ABSOLUTE "${lib}")
                    string(REGEX REPLACE "^/" "-" lib "${lib}")
                    list(APPEND external "${lib}")
                    continue()
                endif()
                string(REGEX REPLACE "^-l" "" lib "${lib}")
                string(TOLOWER "${lib}" _lower)
                if(_lower IN_LIST _skip_list)
                    if(NOT _lower STREQUAL short_name AND NOT _lower IN_LIST _closure)
                        message(FATAL_ERROR "${pkgmod} links FFmpeg module ${lib} absent from its dependency graph")
                    endif()
                else()
                    ffmpeg_classify_library(_entry "${lib}" "${cfg}" ${_search_dirs})
                    list(APPEND external "${_entry}")
                endif()
            endforeach()
        else()
            # Preserve the original non-MSVC metadata behavior.
            list(FILTER libs EXCLUDE REGEX "^-F.+")
            list(FILTER libs EXCLUDE REGEX "^-framework$")
            list(FILTER libs EXCLUDE REGEX "^-L.+")
            list(FILTER libs EXCLUDE REGEX "^-libpath:.+")
            list(TRANSFORM libs REPLACE "^-Wl,-framework," "-l")
            list(FILTER libs EXCLUDE REGEX "^-Wl,.+")
            list(TRANSFORM libs REPLACE "^-l" "")
            if(VCPKG_TARGET_IS_WINDOWS)
                list(TRANSFORM libs TOLOWER)
            endif()
            foreach(lib IN LISTS libs)
                if(lib IN_LIST _skip_list)
                    if(NOT lib STREQUAL short_name AND NOT lib IN_LIST _closure)
                        message(FATAL_ERROR "${pkgmod} links FFmpeg module ${lib} absent from its dependency graph")
                    endif()
                else()
                    list(APPEND external "${lib}")
                endif()
            endforeach()
        endif()
        list(REMOVE_DUPLICATES external)
        set(FFMPEG_${short_name}_LIBRARIES_${cfg} "${external}")
    endforeach()
endforeach()

# 3. Topological sort (Kahn's algorithm)
function(topological_sort out)
    set(available ${ARGN})
    set(sorted "")
    foreach(mod IN LISTS available)
        set(DEPS_${mod} ${FFMPEG_${mod}_DEPS})
    endforeach()
    while(available)
        set(found FALSE)
        foreach(mod IN LISTS available)
            set(has_dep FALSE)
            foreach(d IN LISTS DEPS_${mod})
                if(d IN_LIST available)
                    set(has_dep TRUE)
                    break()
                endif()
            endforeach()
            if(NOT has_dep)
                list(APPEND sorted "${mod}")
                list(REMOVE_ITEM available "${mod}")
                set(found TRUE)
                break()
            endif()
        endforeach()
        if(NOT found)
            message(FATAL_ERROR "Circular dependency detected in FFmpeg modules: ${available}")
        endif()
    endwhile()
    set("${out}" "${sorted}" PARENT_SCOPE)
endfunction()

set(_enabled_modules "")
foreach(pkgmod IN LISTS FFMPEG_PKGCONFIG_MODULES)
    string(REGEX REPLACE "^lib" "" name "${pkgmod}")
    list(APPEND _enabled_modules "${name}")
endforeach()
topological_sort(FFMPEG_TOPO_ORDER ${_enabled_modules})
message(STATUS "Module topological order: ${FFMPEG_TOPO_ORDER}")

# 4. Remove transitive external deps (reverse topo: root → leaf)
list(REVERSE FFMPEG_TOPO_ORDER)
foreach(mod IN LISTS FFMPEG_TOPO_ORDER)
    foreach(dep IN LISTS FFMPEG_${mod}_DEPS)
        foreach(cfg RELEASE DEBUG)
            if(DEFINED FFMPEG_${dep}_LIBRARIES_${cfg})
                list(REMOVE_ITEM FFMPEG_${mod}_LIBRARIES_${cfg}
                     ${FFMPEG_${dep}_LIBRARIES_${cfg}})
            endif()
        endforeach()
    endforeach()
endforeach()
list(REVERSE FFMPEG_TOPO_ORDER)

# 5. Log results
foreach(mod IN LISTS FFMPEG_TOPO_ORDER)
    message(STATUS "FFMPEG_${mod}_DEPS: ${FFMPEG_${mod}_DEPS}")
    message(STATUS "FFMPEG_${mod}_LIBRARIES_RELEASE: ${FFMPEG_${mod}_LIBRARIES_RELEASE}")
    message(STATUS "FFMPEG_${mod}_LIBRARIES_DEBUG: ${FFMPEG_${mod}_LIBRARIES_DEBUG}")
endforeach()

# 6. Encode actual vcpkg library files as configuration-relative references.
# MSVC system libraries remain names for the linker.  A missing library in
# one configuration must not be resolved from the other configuration.
# The installed file inventory also identifies a dependency whose archive
# was removed after installation. Do not scan manual-link directories by
# basename: vcpkg intentionally excludes them from automatic linking.
set(FFMPEG_MODULES "${FFMPEG_TOPO_ORDER}")
set(FFMPEG_MODULE_METADATA "")
foreach(mod IN LISTS FFMPEG_MODULES)
    ffmpeg_pkgconf_run(_version RELEASE --modversion "lib${mod}")
    ffmpeg_pkgconf_run(_debug_version DEBUG --modversion "lib${mod}")
    if(NOT _version MATCHES "^[0-9]+[.][0-9]+[.][0-9]+$" OR NOT _version STREQUAL _debug_version)
        message(FATAL_ERROR "Invalid or inconsistent FFmpeg module version: ${mod}")
    endif()
    if(mod STREQUAL "postproc")
        set(_header "postprocess.h")
    else()
        set(_header "${mod}.h")
    endif()
    if(NOT EXISTS "${CURRENT_PACKAGES_DIR}/include/lib${mod}/${_header}")
        message(FATAL_ERROR "Missing FFmpeg public header: lib${mod}/${_header}")
    endif()
    foreach(cfg RELEASE DEBUG)
        set(_metadata_${cfg} "${FFMPEG_${mod}_LIBRARIES_${cfg}}")
    endforeach()
    set(_metadata_VERSION "${_version}")
    set(FFMPEG_${mod}_MODULE_VERSION "${_version}")
    set(_metadata_HEADER "${_header}")
    set(_metadata_DEPS "${FFMPEG_${mod}_DEPS}")
    foreach(field VERSION HEADER DEPS RELEASE DEBUG)
        # Literal bracket arguments prevent expansion of generated data.
        if(_metadata_${field} MATCHES "\\]==\\]")
            message(FATAL_ERROR "Unsupported FFmpeg metadata delimiter")
        endif()
        string(APPEND FFMPEG_MODULE_METADATA
            "set(_ff_${mod}_${field} [==[${_metadata_${field}}]==])\n")
    endforeach()
endforeach()
# END module dependency metadata

# This is a native paired Port, not an extracted public Binary SDK.
# Validate its actual MSVC install layout after DEF conversion and fixup.
if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)
    foreach(_mod IN LISTS FFMPEG_MODULES)
        string(REGEX MATCH "^[0-9]+" _major "${FFMPEG_${_mod}_MODULE_VERSION}")
        foreach(_cfg RELEASE DEBUG)
            set(_prefix "${CURRENT_PACKAGES_DIR}")
            if(_cfg STREQUAL "DEBUG")
                string(APPEND _prefix "/debug")
            endif()
            if(NOT EXISTS "${_prefix}/lib/${_mod}.lib")
                if(NOT _cfg STREQUAL "DEBUG" OR NOT EXISTS "${_prefix}/lib/${_mod}d.lib")
                    message(FATAL_ERROR "FFmpeg ${_cfg}: missing ${_mod} library/archive")
                endif()
            endif()
            if(VCPKG_LIBRARY_LINKAGE STREQUAL "dynamic" AND NOT EXISTS "${_prefix}/bin/${_mod}-${_major}.dll")
                message(FATAL_ERROR "FFmpeg ${_cfg}: missing ${_mod} DLL")
            endif()
        endforeach()
    endforeach()
endif()

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

extract_regex_from_file(FFMPEG_VERSION_FULL
    FILE_WITHOUT_EXTENSION "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-rel/libavutil/ffversion"
    REGEX "#define FFMPEG_VERSION[ ]+\"(.+)\""
)

# ========== 25. Copyright handling ==========

foreach(_cfg rel dbg)
    file(STRINGS
        "${CURRENT_BUILDTREES_DIR}/build-${TARGET_TRIPLET}-${_cfg}-out.log"
        _ff_license_${_cfg}
        REGEX "License: .*"
        LIMIT_COUNT 1
    )
    string(STRIP "${_ff_license_${_cfg}}" _ff_license_${_cfg})
    if(NOT _ff_license_${_cfg})
        message(FATAL_ERROR "FFmpeg ${_cfg}: missing Configure license evidence")
    endif()
endforeach()
if(NOT _ff_license_rel STREQUAL _ff_license_dbg)
    message(FATAL_ERROR "FFmpeg license differs between Release (${_ff_license_rel}) and Debug (${_ff_license_dbg})")
endif()
set(LICENSE_STRING "${_ff_license_rel}")
# This recipe explicitly enables version3 for both configurations.
# A version2 result would contradict the requested licensing mode.
if("license-nonfree" IN_LIST FEATURES)
    set(_ff_expected_license "^License: nonfree and unredistributable$")
elseif("license-gpl" IN_LIST FEATURES)
    set(_ff_expected_license "^License: GPL version 3 or later$")
else()
    set(_ff_expected_license "^License: LGPL version 3 or later$")
endif()
if(NOT LICENSE_STRING MATCHES "${_ff_expected_license}")
    message(FATAL_ERROR "FFmpeg license does not match the requested license features: ${LICENSE_STRING}")
endif()

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

# ========== 26. CMake package interfaces + usage generation ==========

include("${FFMPEG_SHARED_DIR}/package-config.cmake")
ffmpeg_install_cmake_package("${CURRENT_PACKAGES_DIR}/share/ffmpeg")

configure_file(
    "${FFMPEG_SHARED_DIR}/vcpkg-cmake-wrapper.cmake"
    "${CURRENT_PACKAGES_DIR}/share/ffmpeg/vcpkg-cmake-wrapper.cmake"
    @ONLY
)

file(INSTALL
    "${CURRENT_PORT_DIR}/usage"
    DESTINATION "${CURRENT_PACKAGES_DIR}/share/ffmpeg"
)

if(VCPKG_LIBRARY_LINKAGE STREQUAL "static"
   AND NOT VCPKG_TARGET_IS_WINDOWS
   AND NOT VCPKG_TARGET_IS_OSX
   AND NOT VCPKG_TARGET_IS_IOS)
    file(APPEND "${CURRENT_PACKAGES_DIR}/share/ffmpeg/usage" "
To use the static libraries to build your own shared library,
you may need to add the following link option for your library:

  -Wl,-Bsymbolic
")
endif()

# ========== 27. Install copyright ==========

vcpkg_install_copyright(FILE_LIST "${SOURCE_PATH}/${LICENSE_FILE}")
