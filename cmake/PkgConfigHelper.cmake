macro(convert_libs_to_flags _input_list _output_str)
    set(_tmp_list "")
    if(${_input_list})
        foreach(_lib ${${_input_list}})
            if(NOT _lib MATCHES "^-")
                list(APPEND _tmp_list "-l${_lib}")
            else()
                list(APPEND _tmp_list "${_lib}")
            endif()
        endforeach()
    endif()
    string(REPLACE ";" " " ${_output_str} "${_tmp_list}")
endmacro()

macro(add_pkgconfig_file _target _pc_file _lib_name _version _description)
    cmake_parse_arguments(_pc 
        ""
        "INCLUDE_DIR;CFLAGS"
        "REQUIRES;REQUIRES_PRIVATE;LIBS;LIBS_PRIVATE"
        ${ARGN}
    )

    set(_req "")
    if(_pc_REQUIRES)
        string(REPLACE ";" " " _req_str "${_pc_REQUIRES}")
        set(_req "Requires: ${_req_str}\n")
    endif()

    set(_req_private "")
    if(_pc_REQUIRES_PRIVATE)
        string(REPLACE ";" " " _req_private_str "${_pc_REQUIRES_PRIVATE}")
        set(_req_private "Requires.private: ${_req_private_str}\n")
    endif()

    set(_inc "\${includedir}")
    if(_pc_INCLUDE_DIR)
        set(_inc "\${includedir}/${_pc_INCLUDE_DIR}")
    endif()

    set(_cflags "-I${_inc}")
    if(_pc_CFLAGS)
        set(_cflags "${_cflags} ${_pc_CFLAGS}")
    endif()

    set(_libs "-L\${libdir} -l${_lib_name}")
    if(_pc_LIBS)
        convert_libs_to_flags(_pc_LIBS _libs_str)
        set(_libs "${_libs} ${_libs_str}")
    endif()

    set(_libs_private "")
    if(_pc_LIBS_PRIVATE)
        convert_libs_to_flags(_pc_LIBS_PRIVATE _libs_private_str)
        set(_libs_private "Libs.private: ${_libs_private_str}\n")
    endif()

    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/${_pc_file}"
        "prefix=${STAGE_DIR}\n"
        "exec_prefix=\${prefix}\n"
        "libdir=\${exec_prefix}/lib\n"
        "includedir=\${prefix}/include\n"
        "\n"
        "Name: ${_lib_name}\n"
        "Description: ${_description}\n"
        "Version: ${_version}\n"
        "${_req}"
        "${_req_private}"
        "Conflicts:\n"
        "Libs: ${_libs}\n"
        "${_libs_private}"
        "Cflags: ${_cflags}\n"
    )
    
    ExternalProject_Add_Step(${_target} ${_lib_name}_pc
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_BINARY_DIR}/${_pc_file}"
            "${STAGE_DIR}/lib/pkgconfig/${_pc_file}"
        DEPENDEES install
    )
endmacro()

# ---- add_rename_step(target from to) ----
# macro(add_rename_step _target _from _to)
#     ExternalProject_Add_Step(${_target} rename
#         COMMAND ${CMAKE_COMMAND} -E rename
#             "${STAGE_DIR}/lib/${_from}"
#             "${STAGE_DIR}/lib/${_to}"
#         DEPENDEES install
#     )
# endmacro()

macro(add_rename_step _target _from _to)
    string(REGEX REPLACE "[^a-zA-Z0-9_]" "_" _safe_from_name "${_from}")
    set(_step_name "rename_${_safe_from_name}")
    ExternalProject_Add_Step(${_target} ${_step_name}
        COMMAND ${CMAKE_COMMAND} -E rename
            "${STAGE_DIR}/lib/${_from}"
            "${STAGE_DIR}/lib/${_to}"
        DEPENDEES install
    )
endmacro()



macro(patch_pkg_config _prefix)
    file(GLOB _pcs "${_prefix}/lib/pkgconfig/*.pc")
    file(GLOB _share "${_prefix}/share/pkgconfig/*.pc")
    if(_share)
        list(APPEND _pcs ${_share})
    endif()
    foreach(_pc IN LISTS _pcs)
        file(READ "${_pc}" _content)
        string(REPLACE "${STAGE_DIR}" "\${pcfiledir}/../.." _content "${_content}")
        file(WRITE "${_pc}" "${_content}")
    endforeach()
endmacro()

macro(add_libtool_step _target)
    set(_dest "ltmain.sh")
    if(${ARGC} GREATER 1)
        set(_dest "${ARGV1}")
    endif()
    ExternalProject_Add_Step(${_target} copy_libtool
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_LIST_DIR}/ltmain.sh"
            <SOURCE_DIR>/${_dest}
        DEPENDEES download update patch
        DEPENDERS configure
    )
endmacro()


macro(skip_if_staged_target TARGET_NAME)
    set(options )
    set(oneValueArgs )
    set(multiValueArgs LIBS FILES)
    cmake_parse_arguments(ARG "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    set(_FINAL_LIBS ${ARG_LIBS})
    if(ARG_UNPARSED_ARGUMENTS)
        list(APPEND _FINAL_LIBS ${ARG_UNPARSED_ARGUMENTS})
    endif()
    if(_FINAL_LIBS)
        list(REMOVE_DUPLICATES _FINAL_LIBS)
    endif()
    set(ARG_LIBS ${_FINAL_LIBS})

    set(${TARGET_NAME}_STAGED FALSE)
    if(ARG_LIBS)
        find_package(PkgConfig QUIET)
        set(_all_libs_found TRUE)

        foreach(_lib IN LISTS ARG_LIBS)
            set(_this_lib_found FALSE)

            if(PKG_CONFIG_FOUND)
                unset(_PKG_${_lib}_FOUND CACHE)
                pkg_check_modules(_PKG_${_lib} QUIET "${_lib}")
            endif()

            if(_PKG_${_lib}_FOUND)
                message(STATUS "Found '${_lib}' via pkgconf")
                list(APPEND ${TARGET_NAME}_LINK_LIBRARIES_LOCAL ${_PKG_${_lib}_LIBRARIES})
                include_directories(${_PKG_${_lib}_INCLUDE_DIRS})
                link_directories(${_PKG_${_lib}_LIBRARY_DIRS})
                set(_this_lib_found TRUE) 
            else()
                unset(${_lib}_FOUND CACHE)
                find_package(${_lib} QUIET)
                
                if(${_lib}_FOUND OR ${TARGET_NAME}_FOUND)
                    message(STATUS "Found '${_lib}' via findpkg")
                    if(TARGET ${_lib}::${_lib})
                        list(APPEND ${TARGET_NAME}_LINK_LIBRARIES_LOCAL ${_lib}::${_lib})
                    elseif(TARGET ${_lib})
                        list(APPEND ${TARGET_NAME}_LINK_LIBRARIES_LOCAL ${_lib})
                    elseif(${_lib}_LIBRARIES)
                        list(APPEND ${TARGET_NAME}_LINK_LIBRARIES_LOCAL ${${_lib}_LIBRARIES})
                    endif()
                    set(_this_lib_found TRUE) 
                endif()
            endif()

            if(NOT _this_lib_found)
                # message(STATUS "[skip_if_staged] Component '${_lib}' missing! Blocking cache.")
                set(_all_libs_found FALSE)
                break()
            endif()
        endforeach()

        if(_all_libs_found AND ARG_LIBS)
            set(${TARGET_NAME}_STAGED TRUE)
            set(${TARGET_NAME}_LIBS ${${TARGET_NAME}_LINK_LIBRARIES_LOCAL})
        else()
            set(${TARGET_NAME}_LINK_LIBRARIES_LOCAL "")
        endif()
    endif()

    if(NOT ${TARGET_NAME}_STAGED AND ARG_FILES)
        set(_all_files_exist TRUE)
        foreach(_file IN LISTS ARG_FILES)
            if(NOT EXISTS "${_file}")
                set(_all_files_exist FALSE)
                break()
            endif()
        endforeach()
        
        if(_all_files_exist)
            set(${TARGET_NAME}_STAGED TRUE)
            message(STATUS "[skip_if_staged] Found all specified files via physics disk scan")
            
            set(${TARGET_NAME}_IMPORTED_LIBS "")
            foreach(_file_path IN LISTS ARG_FILES)
                if(_file_path MATCHES "\\.(lib|a|so|dylib)$")
                    get_filename_component(_lib_name "${_file_path}" NAME_WE)
                    set(_imported_target_name "${TARGET_NAME}_${_lib_name}_imported")
                    
                    if(NOT TARGET ${_imported_target_name})
                        add_library(${_imported_target_name} STATIC IMPORTED GLOBAL)
                        set_target_properties(${_imported_target_name} PROPERTIES
                            IMPORTED_LOCATION "${_file_path}"
                        )
                    endif()
                    list(APPEND ${TARGET_NAME}_IMPORTED_LIBS ${_imported_target_name})
                endif()
            endforeach()
            set(${TARGET_NAME}_LIBS ${${TARGET_NAME}_IMPORTED_LIBS})
            set(${TARGET_NAME}_LIBS ${${TARGET_NAME}_IMPORTED_LIBS} PARENT_SCOPE)
        endif()
    endif()

    if(${TARGET_NAME}_STAGED AND NOT FORCE_REBUILD)
        # message(STATUS "[skip_if_staged] Target '${TARGET_NAME}' is ALREADY STAGED. Intercepting graph and breaking outer function.")

        if(NOT TARGET ${TARGET_NAME})
            add_custom_target(${TARGET_NAME})
        endif()

        return()
    # else()
    #     message(STATUS "[skip_if_staged] Target '${TARGET_NAME}' not found anywhere. Granting pass to build pipeline.")
    endif()
endmacro()