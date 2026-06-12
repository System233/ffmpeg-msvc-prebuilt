# DepResolver.cmake — Version matching + dependency resolution

macro(dep_resolve_all)
    # ---- 1. Match FFmpeg version to family ----
    get_property(_all_fam GLOBAL PROPERTY ALL_FAMILIES)
    set(_found_family "")
    foreach(_fam IN LISTS _all_fam)
        get_property(_vm GLOBAL PROPERTY "FAM_${_fam}_VERSION_MATCH")
        get_property(_vr GLOBAL PROPERTY "FAM_${_fam}_VERSION_RANGE")
        if(NOT _vm AND NOT _vr)
            continue()
        endif()
        if(_vm)
            if("${FFMPEG_VERSION}" MATCHES "${_vm}")
                set(_found_family "${_fam}")
                break()
            endif()
        endif()
        if(_vr)
            version_in_range("${FFMPEG_VERSION}" "${_vr}" _in)
            if(_in)
                set(_found_family "${_fam}")
                break()
            endif()
        endif()
    endforeach()
    if("${_found_family}" STREQUAL "")
        message(FATAL_ERROR "No family matches FFmpeg version ${FFMPEG_VERSION}")
    endif()
    message(STATUS "Matched family: ${_found_family}")

    # ---- 2. Resolve FFmpeg URL ----
    get_property(_f_url  GLOBAL PROPERTY "FAM_${_found_family}_URL")
    get_property(_f_tmpl GLOBAL PROPERTY "FAM_${_found_family}_URL_TEMPLATE")
    get_property(_f_type GLOBAL PROPERTY "FAM_${_found_family}_URL_TYPE")
    if(_f_tmpl)
        string(CONFIGURE "${_f_tmpl}" _f_url)
    endif()
    if(NOT _f_url)
        set(_f_url  "https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n${FFMPEG_VERSION}.tar.gz")
        set(_f_type "tarball")
    endif()
    if(NOT _f_type)
        set(_f_type "tarball")
    endif()
    set(FFMPEG_RESOLVED_URL      "${_f_url}")
    set(FFMPEG_RESOLVED_URL_TYPE "${_f_type}")

    # ---- 3. Resolve FFmpeg patches -> PATCH_COMMAND list ----
    get_property(_f_patches GLOBAL PROPERTY "FAM_${_found_family}_PATCHES")
    _dep_build_patch_cmds("ffmpeg" _f_patches FFMPEG_RESOLVED_PATCH_CMDS)

    # ---- 4. FFmpeg configure flags from family ----
    get_property(_f_flags GLOBAL PROPERTY "FAM_${_found_family}_CONFIGURE_FLAGS")
    set(FFMPEG_ASM_FLAGS "${_f_flags}")

    # ---- 5. Parse family DEPS: "zlib>=1.2.0;x264;fribidi>=1.0.0;libass>=0.17.0" ----
    get_property(_deps_raw GLOBAL PROPERTY "FAM_${_found_family}_DEPS")
    set(_deps_list "")
    set(_constraint_ "")   # clear all
    foreach(_entry IN LISTS _deps_raw)
        string(STRIP "${_entry}" _entry)
        if("${_entry}" MATCHES "^(.+)>=(.+)$")
            set(_dep_name "${CMAKE_MATCH_1}")
            set(${_dep_name}_CONSTRAINT ">=${CMAKE_MATCH_2}")
        else()
            set(_dep_name "${_entry}")
        endif()
        list(APPEND _deps_list "${_dep_name}")
    endforeach()

    # ---- 6. Create ENABLE_DEP_* CACHE BOOL (default ON) for each DEPS entry ----
    foreach(_dep IN LISTS _deps_list)
        set(_cache_var "ENABLE_DEP_${_dep}")
        string(TOUPPER "${_cache_var}" _cache_var)
        set(${_cache_var} ON CACHE BOOL "Enable ${_dep} dependency")
    endforeach()

    # ---- 7. License check ----
    if(LICENSE STREQUAL "lgpl")
        foreach(_dep IN LISTS _deps_list)
            get_property(_lic GLOBAL PROPERTY "DEP_${_dep}_LICENSE")
            if(_lic STREQUAL "gpl")
                message(FATAL_ERROR "Dependency '${_dep}' is GPL-licensed, but LICENSE=lgpl")
            endif()
        endforeach()
    endif()

    # ---- 8. Resolve dependencies with transitive closure (DFS) ----
    set(FFMPEG_ASM_DEPENDS "")
    set(RESOLVED_DEPS "")

    foreach(_dep IN LISTS _deps_list)
        _resolve_with_transitives("${_dep}")
    endforeach()

    # ---- Generate ${NAME}_RESOLVED_DEPENDS from REQUIRES ----
    foreach(_dep IN LISTS RESOLVED_DEPS)
        get_property(_reqs GLOBAL PROPERTY "DEP_${_dep}_REQUIRES")
        string(TOUPPER "${_dep}" _dep_upper)
        set(${_dep_upper}_RESOLVED_DEPENDS "")
        if(_reqs)
            foreach(_req IN LISTS _reqs)
                list(APPEND ${_dep_upper}_RESOLVED_DEPENDS "${_req}_target")
            endforeach()
        endif()
    endforeach()

    message(STATUS "Resolved dependencies: ${RESOLVED_DEPS}")
    message(STATUS "FFmpeg flags: ${FFMPEG_ASM_FLAGS}")
endmacro()

# ---- Internal helpers ----

# _resolve_with_transitives(NAME): recursively resolve REQUIRES first, then register dep
# NOTE: uses if/else nesting — macro return() exits caller scope, not just this macro
macro(_resolve_with_transitives _name)
    list(FIND RESOLVED_DEPS "${_name}" _idx)
    if(_idx EQUAL -1)
        set(_cache_var "ENABLE_DEP_${_name}")
        string(TOUPPER "${_cache_var}" _cache_var)
        if(NOT ${_cache_var})
            message(STATUS "  ${_name} = disabled")
        else()
            # Transitives first (depth-first, ensures they appear earlier in RESOLVED_DEPS)
            get_property(_reqs GLOBAL PROPERTY "DEP_${_name}_REQUIRES")
            if(_reqs)
                foreach(_req IN LISTS _reqs)
                    set(_cache_var_r "ENABLE_DEP_${_req}")
                    string(TOUPPER "${_cache_var_r}" _cache_var_r)
                    if(NOT ${_cache_var_r})
                        message(WARNING "Dependency '${_req}' required by '${_name}', auto-enabling")
                        set(${_cache_var_r} ON CACHE BOOL "Enable ${_req} dependency" FORCE)
                    endif()
                    _resolve_with_transitives("${_req}")
                endforeach()
            endif()

            # Register this dep
            list(APPEND RESOLVED_DEPS "${_name}")
            _dep_resolve_single("${_name}")
            list(APPEND FFMPEG_ASM_DEPENDS "${_name}_target")

            get_property(_flag GLOBAL PROPERTY "DEP_${_name}_FFMPEG_FLAG")
            if(_flag)
                list(APPEND FFMPEG_ASM_FLAGS "${_flag}")
            endif()
        endif()
    endif()
endmacro()

macro(_dep_resolve_single _name)
    string(TOUPPER "${_name}" _name_upper)
    # Determine version
    get_property(_def_ver GLOBAL PROPERTY "DEP_${_name}_DEFAULT")
    set(_ver "${_def_ver}")

    if(DEP_VERSION_OVERRIDE)
        foreach(_ov IN LISTS DEP_VERSION_OVERRIDE)
            if("${_ov}" MATCHES "^${_name}=(.+)$")
                set(_ver "${CMAKE_MATCH_1}")
                break()
            endif()
        endforeach()
    endif()

    # Check family constraint (from DEPS inline "name>=ver")
    if(DEFINED ${_name_upper}_CONSTRAINT)
        version_satisfies("${_ver}" "${${_name_upper}_CONSTRAINT}" _satisfied)
        if(NOT _satisfied)
            message(FATAL_ERROR "Dependency '${_name}' version '${_ver}' violates family constraint: ${${_name_upper}_CONSTRAINT}")
        endif()
    endif()

    # Lookup URL + patches
    string(MAKE_C_IDENTIFIER "${_name}_${_ver}" _key)
    get_property(_url  GLOBAL PROPERTY "DEP_${_key}_URL")
    get_property(_url_type GLOBAL PROPERTY "DEP_${_key}_URL_TYPE")
    get_property(_patches   GLOBAL PROPERTY "DEP_${_key}_PATCHES")

    if(NOT _url)
        message(FATAL_ERROR "Unknown version '${_ver}' for dependency '${_name}'")
    endif()


    set(${_name_upper}_RESOLVED_VERSION      "${_ver}")
    set(${_name_upper}_RESOLVED_URL      "${_url}")
    set(${_name_upper}_RESOLVED_URL_TYPE "${_url_type}")
    
    string(REGEX REPLACE "\\?.*$" "" _clean_url "${_url}")
    cmake_path(GET _clean_url FILENAME _filename)
    set(${_name_upper}_RESOLVED_DOWNLOAD_NAME "${_name}_${_filename}")

    _dep_build_patch_cmds("${_name}" _patches ${_name_upper}_RESOLVED_PATCH_CMDS)

    message(STATUS "  ${_name} = ${_ver} (${_url_type})")
endmacro()

macro(_dep_build_patch_cmds _dn _plist _outvar)
    set(_cmds "")
    if(${_plist})
        foreach(_p IN LISTS ${_plist})
            set(_pf "${CMAKE_SOURCE_DIR}/patches/${_p}")
            list(APPEND _cmds COMMAND patch -N -p1 -d <SOURCE_DIR> -i "${_pf}")
        endforeach()
    endif()
    set(${_outvar} "${_cmds}")
endmacro()
