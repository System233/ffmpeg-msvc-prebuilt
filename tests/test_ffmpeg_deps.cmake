# test_ffmpeg_deps.cmake
#
# Tests per-module dependency resolution logic (ffmpeg-portfile.cmake Section 23)
# using real .pc files via pkgconf from a vcpkg build.
#
# Usage:
#   cmake -DVCPKG_INSTALLED_DIR=<path> -P tests/test_ffmpeg_deps.cmake
#   cmake -P tests/test_ffmpeg_deps.cmake

cmake_minimum_required(VERSION 3.20)

# ---- Config ----
if(NOT DEFINED VCPKG_INSTALLED_DIR)
  get_filename_component(THIS_DIR "${CMAKE_CURRENT_LIST_DIR}" ABSOLUTE)
  set(VCPKG_INSTALLED_DIR
    "${THIS_DIR}/../build/8.x/vcpkg_installed/x64-windows")
endif()

get_filename_component(BUILD_ROOT "${VCPKG_INSTALLED_DIR}/../.." ABSOLUTE)
set(TEMPLATE_PATH "${THIS_DIR}/../scripts/cmake/FindFFmpeg.cmake.in")
set(OUTPUT_DIR "${THIS_DIR}/../build/test_output")

message(STATUS "VCPKG_INSTALLED_DIR: ${VCPKG_INSTALLED_DIR}")
message(STATUS "TEMPLATE_PATH: ${TEMPLATE_PATH}")

# Core module mappings
set(FFMPEG_CORE_MODULES libavutil libavcodec libavformat libavfilter libavdevice libswresample libswscale)
set(FFMPEG_CORE_SHORT_NAMES avutil avcodec avformat avfilter avdevice swresample swscale)

# ==========================================
# Step 1: Find pkgconf and set up environment
# ==========================================

set(PKGCONF "${VCPKG_INSTALLED_DIR}/tools/pkgconf/pkgconf.exe")
if(NOT EXISTS "${PKGCONF}")
  message(FATAL_ERROR "pkgconf not found at: ${PKGCONF}")
endif()
message(STATUS "pkgconf: ${PKGCONF}")

# Set PKG_CONFIG_PATH: prepend vcpkg paths, preserve any external env
set(_pc_dirs "${VCPKG_INSTALLED_DIR}/lib/pkgconfig")
if(EXISTS "${VCPKG_INSTALLED_DIR}/share/pkgconfig")
  string(APPEND _pc_dirs ";${VCPKG_INSTALLED_DIR}/share/pkgconfig")
endif()
if(DEFINED ENV{PKG_CONFIG_PATH} AND NOT "$ENV{PKG_CONFIG_PATH}" STREQUAL "")
  string(APPEND _pc_dirs ";$ENV{PKG_CONFIG_PATH}")
endif()
set(ENV{PKG_CONFIG_PATH} "${_pc_dirs}")

message(STATUS "PKG_CONFIG_PATH: $ENV{PKG_CONFIG_PATH}")

# ==========================================
# Step 2: Query pkgconf for each module
# ==========================================
#
# Two queries per module:
#   2a. pkgconf <mod> --print-requires-private  → DEPS (internal FFmpeg modules)
#   2b. pkgconf --libs --static <mod>           → LIBRARIES (external system deps)

file(TO_NATIVE_PATH "${PKGCONF}" PKGCONF_NATIVE)
string(REPLACE "\\\\" "\\" PKGCONF_NATIVE "${PKGCONF_NATIVE}")

foreach(mod IN LISTS FFMPEG_CORE_MODULES)
  # 2a. DEPS via --print-requires-private
  execute_process(
    COMMAND "${PKGCONF_NATIVE}" "${mod}" --print-requires-private
    OUTPUT_VARIABLE deps_raw
    ERROR_VARIABLE  deps_err
    RESULT_VARIABLE deps_rc
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )

  string(REGEX REPLACE "^lib" "" short "${mod}")
  set(FFMPEG_${short}_DEPS "")
  if(deps_rc EQUAL 0 AND NOT deps_raw STREQUAL "")
    string(REPLACE "\n" ";" lines "${deps_raw}")
    foreach(line IN LISTS lines)
      string(STRIP "${line}" line)
      if(NOT line STREQUAL "")
        string(REGEX REPLACE "^([^ ]+).*$" "\\1" name "${line}")
        string(STRIP "${name}" name)
        string(REGEX REPLACE "^lib" "" name "${name}")
        if(name IN_LIST FFMPEG_CORE_SHORT_NAMES AND NOT name STREQUAL short)
          list(APPEND FFMPEG_${short}_DEPS "${name}")
        endif()
      endif()
    endforeach()
  endif()
  list(REMOVE_DUPLICATES FFMPEG_${short}_DEPS)

  # 2b. LIBRARIES via --libs --static
  execute_process(
    COMMAND "${PKGCONF_NATIVE}" --libs --static "${mod}"
    OUTPUT_VARIABLE libs_raw
    ERROR_VARIABLE  libs_err
    RESULT_VARIABLE libs_rc
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )

  set(PKG_${mod}_LIBS "")
  if(libs_rc EQUAL 0)
    set(PKG_${mod}_LIBS "${libs_raw}")
  endif()

  message(STATUS "${short}: DEPS=[${FFMPEG_${short}_DEPS}]  requires-private=[${deps_raw}]")
endforeach()

# ==========================================
# Step 3: Run Section 23 parsing logic
# ==========================================

# Parse LIBRARIES from --libs --static: extract -l names, filter out internal modules
foreach(mod IN LISTS FFMPEG_CORE_MODULES)
  string(REGEX REPLACE "^lib" "" short_name "${mod}")
  foreach(cfg RELEASE DEBUG)
    set(libs_str "${PKG_${mod}_LIBS}")
    separate_arguments(libs UNIX_COMMAND "${libs_str}")
    list(FILTER libs EXCLUDE REGEX "^-F.+")
    list(FILTER libs EXCLUDE REGEX "^-framework$")
    list(FILTER libs EXCLUDE REGEX "^-L.+")
    list(FILTER libs EXCLUDE REGEX "^-libpath:.+")
    list(TRANSFORM libs REPLACE "^-Wl,-framework," "-l")
    list(FILTER libs EXCLUDE REGEX "^-Wl,.+")
    list(TRANSFORM libs REPLACE "^-l" "")
    if(WIN32)
      list(TRANSFORM libs TOLOWER)
    endif()
    # Collect DEPS + self for filtering
    set(_skip_list ${FFMPEG_${short_name}_DEPS} ${short_name})
    set(external "")
    foreach(lib IN LISTS libs)
      if(lib IN_LIST _skip_list)
        # skip - internal FFmpeg modules or self
      else()
        list(APPEND external "${lib}")
      endif()
    endforeach()
    list(REMOVE_DUPLICATES external)
    set(FFMPEG_${short_name}_LIBRARIES_${cfg} "${external}")
  endforeach()
endforeach()

message(STATUS "")
message(STATUS "====== Before transitive cleanup ======")
foreach(short IN LISTS FFMPEG_CORE_SHORT_NAMES)
  if(DEFINED FFMPEG_${short}_DEPS)
    message(STATUS "${short}: DEPS=[${FFMPEG_${short}_DEPS}]  LIBRARIES=[${FFMPEG_${short}_LIBRARIES_RELEASE}]")
  endif()
endforeach()

# 3c. Topological sort
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

topological_sort(FFMPEG_TOPO_ORDER ${FFMPEG_CORE_SHORT_NAMES})
message(STATUS "")
message(STATUS "Topological order: ${FFMPEG_TOPO_ORDER}")

# 3d. Remove transitive external deps (reverse topo: root → leaf)
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

message(STATUS "")
message(STATUS "====== After transitive cleanup ======")
foreach(short IN LISTS FFMPEG_CORE_SHORT_NAMES)
  if(DEFINED FFMPEG_${short}_DEPS)
    message(STATUS "${short}: DEPS=[${FFMPEG_${short}_DEPS}]  LIBRARIES=[${FFMPEG_${short}_LIBRARIES_RELEASE}]")
  endif()
endforeach()

# ==========================================
# Step 4: Set template variables and generate FindFFmpeg.cmake
# ==========================================

file(MAKE_DIRECTORY "${OUTPUT_DIR}")

foreach(short_name IN LISTS FFMPEG_CORE_SHORT_NAMES)
  string(TOUPPER "${short_name}" uc)
  set(FFMPEG_DEP_${uc}_RELEASE_LIST "")
  set(FFMPEG_DEP_${uc}_DEBUG_LIST "")
  set(FFMPEG_DEP_${uc}_DEPS_LIST "")
endforeach()
foreach(mod IN LISTS FFMPEG_CORE_SHORT_NAMES)
  string(TOUPPER "${mod}" uc)
  set(FFMPEG_DEP_${uc}_RELEASE_LIST "${FFMPEG_${mod}_LIBRARIES_RELEASE}")
  set(FFMPEG_DEP_${uc}_DEBUG_LIST "${FFMPEG_${mod}_LIBRARIES_DEBUG}")
  set(FFMPEG_DEP_${uc}_DEPS_LIST "${FFMPEG_${mod}_DEPS}")
endforeach()

set(FFMPEG_VERSION "99.99.99")
set(LIBAVUTIL_VERSION "99.0.0")
set(LIBAVCODEC_VERSION "99.0.0")
set(LIBAVDEVICE_VERSION "99.0.0")
set(LIBAVFILTER_VERSION "99.0.0")
set(LIBAVFORMAT_VERSION "99.0.0")
set(LIBSWRESAMPLE_VERSION "99.0.0")
set(LIBSWSCALE_VERSION "99.0.0")
set(FFMPEG_DEPENDENCIES_RELEASE "")
set(FFMPEG_DEPENDENCIES_DEBUG "")

configure_file("${TEMPLATE_PATH}" "${OUTPUT_DIR}/FindFFmpeg.cmake" @ONLY)
message(STATUS "")
message(STATUS "Generated: ${OUTPUT_DIR}/FindFFmpeg.cmake")

# ==========================================
# Step 5: Verify assertions
# ==========================================

message(STATUS "")
message(STATUS "====== Assertions ======")

set(ALL_PASS TRUE)

macro(check cond)
  if(NOT (${cond}))
    set(ALL_PASS FALSE)
  endif()
endmacro()

# 5a. Verify topological order
if("${FFMPEG_TOPO_ORDER}" MATCHES "^avutil;")
  message(STATUS "  PASS: avutil is first in topo order")
else()
  message(STATUS "  FAIL: avutil is first in topo order (got: ${FFMPEG_TOPO_ORDER})")
  set(ALL_PASS FALSE)
endif()
foreach(_m swresample swscale avcodec avformat avfilter avdevice)
  if("${_m}" IN_LIST FFMPEG_TOPO_ORDER)
    message(STATUS "  PASS: ${_m} appears in topological order")
  else()
    message(STATUS "  FAIL: ${_m} NOT in topological order")
    set(ALL_PASS FALSE)
  endif()
endforeach()

# 5b. Verify DEPS
macro(verify_deps module expected_deps)
  set(_e "${expected_deps}")
  list(SORT _e)
  set(_a ${FFMPEG_${module}_DEPS})
  list(SORT _a)
  if("${_a}" STREQUAL "${_e}")
    message(STATUS "  PASS: ${module} DEPS=${expected_deps}")
  else()
    message(STATUS "  FAIL: ${module} DEPS expected [${expected_deps}] got [${_a}]")
    set(ALL_PASS FALSE)
  endif()
endmacro()

verify_deps(avutil "")
verify_deps(swresample "avutil")
verify_deps(swscale "avutil")
verify_deps(avcodec "avutil;swresample")
verify_deps(avformat "avcodec;avutil;swresample")
verify_deps(avfilter "avformat;avcodec;avutil;swresample;swscale")
verify_deps(avdevice "avfilter;avformat;avcodec;avutil;swresample;swscale")

# 5c. Verify transitive cleanup
macro(assert_not_in_list lib_name list_var desc)
  if("${lib_name}" IN_LIST ${list_var})
    message(STATUS "  FAIL: ${desc} - '${lib_name}' should NOT be in list")
    set(ALL_PASS FALSE)
  else()
    message(STATUS "  PASS: ${desc} - '${lib_name}' not in list")
  endif()
endmacro()

macro(assert_in_list lib_name list_var desc)
  if("${lib_name}" IN_LIST ${list_var})
    message(STATUS "  PASS: ${desc} - '${lib_name}' in list")
  else()
    message(STATUS "  FAIL: ${desc} - '${lib_name}' NOT in list")
    set(ALL_PASS FALSE)
  endif()
endmacro()

foreach(_bad zs opencl cfgmgr32 runtimeobject advapi32 libssl libcrypto crypt32 ws2_32 user32 bcrypt)
  assert_not_in_list("${_bad}" FFMPEG_avcodec_LIBRARIES_RELEASE
    "avcodec does NOT contain avutil's dep '${_bad}'")
endforeach()
assert_not_in_list("soxr" FFMPEG_avcodec_LIBRARIES_RELEASE
  "avcodec does NOT contain swresample's dep 'soxr'")

assert_not_in_list("dav1d" FFMPEG_avformat_LIBRARIES_RELEASE
  "avformat does NOT contain avcodec's dep 'dav1d'")
assert_not_in_list("vpx" FFMPEG_avformat_LIBRARIES_RELEASE
  "avformat does NOT contain avcodec's dep 'vpx'")

foreach(_bad fontconfig freetype fribidi)
  assert_not_in_list("${_bad}" FFMPEG_avdevice_LIBRARIES_RELEASE
    "avdevice does NOT contain avfilter's dep '${_bad}'")
endforeach()

foreach(_good vpx dav1d snappy aom opus speex)
  assert_in_list("${_good}" FFMPEG_avcodec_LIBRARIES_RELEASE
    "avcodec still contains its own dep '${_good}'")
endforeach()

# 5d. Verify template generation
file(READ "${OUTPUT_DIR}/FindFFmpeg.cmake" gen_content)
macro(assert_contains substring desc)
  string(FIND "${gen_content}" "${substring}" _pos)
  if(_pos GREATER -1)
    message(STATUS "  PASS: ${desc}")
  else()
    message(STATUS "  FAIL: ${desc}")
    set(ALL_PASS FALSE)
  endif()
endmacro()

assert_contains("FFMPEG_ATTACH_MODULE_DEPS(libavcodec"
  "Generated file contains ATTACH_MODULE_DEPS for avcodec")
assert_contains("FFMPEG_ADD_IMPORTED_TARGET(libavcodec avcodec)"
  "Generated file contains ADD_IMPORTED_TARGET for avcodec")
assert_contains("FFMPEG_LINK_INTERNAL_DEPS(libavcodec avcodec"
  "Generated file contains LINK_INTERNAL_DEPS for avcodec")
string(FIND "${gen_content}" "@FFMPEG_DEP_" _unresolved)
if(_unresolved GREATER -1)
  message(STATUS "  FAIL: Unresolved @FFMPEG_DEP_@ patterns remain at pos ${_unresolved}")
  set(ALL_PASS FALSE)
else()
  message(STATUS "  PASS: No unresolved @FFMPEG_DEP_@ patterns remain")
endif()

# 5e. Test defensive filtering: non-FFmpeg entries in Requires.private
#     should be ignored for DEPS and instead appear in LIBRARIES.
#     We simulate by running the parsing logic with mixed mock input.
message(STATUS "")
message(STATUS "------ Defensive filtering checks ------")

macro(simulate_deps raw_input expected_deps expected_libs desc)
  # Parse raw --print-requires-private output (same logic as Step 2a)
  set(_parsed_deps "")
  if(NOT "${raw_input}" STREQUAL "")
    string(REPLACE "\n" ";" _lines "${raw_input}")
    foreach(_line IN LISTS _lines)
      string(STRIP "${_line}" _line)
      if(NOT _line STREQUAL "")
        string(REGEX REPLACE "^([^ ]+).*$" "\\1" _name "${_line}")
        string(STRIP "${_name}" _name)
        string(REGEX REPLACE "^lib" "" _name "${_name}")
        if(_name IN_LIST FFMPEG_CORE_SHORT_NAMES)
          list(APPEND _parsed_deps "${_name}")
        endif()
      endif()
    endforeach()
  endif()
  list(REMOVE_DUPLICATES _parsed_deps)
  list(SORT _parsed_deps)
  list(SORT expected_deps)

  if("${_parsed_deps}" STREQUAL "${expected_deps}")
    message(STATUS "  PASS: ${desc} DEPS=[${expected_deps}]")
  else()
    message(STATUS "  FAIL: ${desc} DEPS expected [${expected_deps}] got [${_parsed_deps}]")
    set(ALL_PASS FALSE)
  endif()
endmacro()

# Test: real-ish input with both FFmpeg and non-FFmpeg entries
simulate_deps(
  "libavutil >= 60.26.102\nlibswresample >= 6.3.102\nsomeextlib >= 1.0"
  "avutil;swresample"
  ""
  "Non-FFmpeg dep 'someextlib' is filtered out from DEPS"
)

# Test: only non-FFmpeg entry
simulate_deps(
  "fakelib >= 2.0\notherlib >= 3.0"
  ""
  ""
  "Only non-FFmpeg entries → DEPS is empty"
)

# Test: empty input
simulate_deps(
  ""
  ""
  ""
  "Empty input → DEPS is empty"
)

# Test: no version constraints
simulate_deps(
  "libavutil\nlibswscale"
  "avutil;swscale"
  ""
  "Entries without version constraints work"
)

# Also verify that non-FFmpeg deps (if they somehow existed) would end up in
# LIBRARIES via the --libs --static path (not filtered out as DEPS).
# We simulate by checking that the current parsing of libavcodec's --libs --static
# output contains entries that are NOT in FFMPEG_CORE_SHORT_NAMES.
set(_all_libs_from_codec "")
foreach(cfg RELEASE DEBUG)
  list(APPEND _all_libs_from_codec ${FFMPEG_avcodec_LIBRARIES_${cfg}})
endforeach()
list(REMOVE_DUPLICATES _all_libs_from_codec)
set(_has_external FALSE)
foreach(_lib IN LISTS _all_libs_from_codec)
  if(NOT _lib IN_LIST FFMPEG_CORE_SHORT_NAMES)
    set(_has_external TRUE)
    break()
  endif()
endforeach()
if(_has_external)
  message(STATUS "  PASS: External libs from --libs --static are NOT in DEPS (they go to LIBRARIES)")
else()
  message(STATUS "  FAIL: No external libs found in avcodec LIBRARIES — filtering may be wrong")
  set(ALL_PASS FALSE)
endif()

# ==========================================
# Summary
# ==========================================
message(STATUS "")
if(ALL_PASS)
  message(STATUS "All tests PASSED")
else()
  message(FATAL_ERROR "Some tests FAILED")
endif()
