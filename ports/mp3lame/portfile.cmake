vcpkg_from_sourceforge(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO lame/lame
    REF ${VERSION}
    FILENAME "lame-${VERSION}.tar.gz"
    SHA512 0844b9eadb4aacf8000444621451277de365041cc1d97b7f7a589da0b7a23899310afd4e4d81114b9912aa97832621d20588034715573d417b2923948c08634b
    PATCHES
        00001-msvc-upgrade-solution-up-to-vc11.patch
        remove_lame_init_old_from_symbol_list.patch # deprecated https://github.com/zlargon/lame/blob/master/include/lame.h#L169
        add-macos-universal-config.patch
        fix-mingw-w64-compatibility.patch
        disable-mpglib.patch
)

# This overlay builds the encoding library only. The LAME frontend relies on
# decoder APIs and must not silently reintroduce MPGLIB.
if("frontend" IN_LIST FEATURES)
    message(FATAL_ERROR "The mp3lame overlay does not support the decoder-dependent frontend feature")
endif()

if(VCPKG_TARGET_IS_WINDOWS AND NOT VCPKG_TARGET_IS_MINGW)

    if(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm64")
        set(platform "ARM64")
        set(machine "ARM64")
    elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm")
        set(platform "ARM")
        set(machine "ARM")
    elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
        set(platform "x64")
        set(machine "x64")
    else()
        set(platform "Win32")
        set(machine "x86")
    endif()

    file(READ "${SOURCE_PATH}/vc_solution/vc11_lame.sln" sln_con)
    string(REPLACE "|Win32" "|${platform}" sln_con "${sln_con}")
    string(REPLACE "\"vc11_" "\"${machine}_vc11_" sln_con "${sln_con}")
    file(WRITE "${SOURCE_PATH}/vc_solution/${machine}_vc11_lame.sln" "${sln_con}")

    
    file(GLOB vcxprojs RELATIVE "${SOURCE_PATH}/vc_solution" "${SOURCE_PATH}/vc_solution/vc11_*.vcxproj")
    foreach(vcxproj ${vcxprojs})
        file(READ "${SOURCE_PATH}/vc_solution/${vcxproj}" vcxproj_con)
        
        if(NOT VCPKG_CRT_LINKAGE STREQUAL "dynamic")
            string(REPLACE "DLL</RuntimeLibrary>" "</RuntimeLibrary>" vcxproj_con "${vcxproj_con}")
        endif()

        string(REPLACE "/machine:x86" "/machine:${machine}" vcxproj_con "${vcxproj_con}")
        string(REPLACE "<Platform>Win32</Platform>" "<Platform>${platform}</Platform>" vcxproj_con "${vcxproj_con}")
        string(REPLACE "|Win32" "|${platform}" vcxproj_con "${vcxproj_con}")
        string(REPLACE "Include=\"vc11_" "Include=\"${machine}_vc11_" vcxproj_con "${vcxproj_con}")
 
        if(NOT VCPKG_TARGET_IS_UWP)
            string(REPLACE "/APPCONTAINER" "" vcxproj_con "${vcxproj_con}")
        endif()
        
        file(WRITE "${SOURCE_PATH}/vc_solution/${machine}_${vcxproj}" "${vcxproj_con}")
    endforeach()

    if(VCPKG_LIBRARY_LINKAGE STREQUAL "static")
        vcpkg_msbuild_install(
            SOURCE_PATH "${SOURCE_PATH}"
            PROJECT_SUBPATH "vc_solution/${machine}_vc11_lame.sln"
            TARGET "libmp3lame-static"
            PLATFORM "${platform}"
        )
    else()
        vcpkg_msbuild_install(
            SOURCE_PATH "${SOURCE_PATH}"
            PROJECT_SUBPATH "vc_solution/${machine}_vc11_lame.sln"
            TARGET "libmp3lame"
            PLATFORM "${platform}"
        )
    endif()
    if("frontend" IN_LIST FEATURES)
        vcpkg_msbuild_install(
            SOURCE_PATH "${SOURCE_PATH}"
            PROJECT_SUBPATH "vc_solution/${machine}_vc11_lame.sln"
            TARGET "lame"
            PLATFORM "${platform}"
        )
    endif()

    file(COPY "${SOURCE_PATH}/include/lame.h" DESTINATION "${CURRENT_PACKAGES_DIR}/include/lame")

    if(VCPKG_LIBRARY_LINKAGE STREQUAL "static")
        file(REMOVE_RECURSE
            "${CURRENT_PACKAGES_DIR}/bin"
            "${CURRENT_PACKAGES_DIR}/lib/libmp3lame.lib"
            "${CURRENT_PACKAGES_DIR}/debug/bin"
            "${CURRENT_PACKAGES_DIR}/debug/lib/libmp3lame.lib"
        )
    else()
        file(REMOVE
            "${CURRENT_PACKAGES_DIR}/lib/libmp3lame-static.lib"
            "${CURRENT_PACKAGES_DIR}/debug/lib/libmp3lame-static.lib"
        )
    endif()

else()

    vcpkg_list(SET OPTIONS)
    if("frontend" IN_LIST FEATURES)
        list(APPEND OPTIONS --enable-frontend)
    else()
        list(APPEND OPTIONS --disable-frontend)
    endif()

    list(APPEND OPTIONS --disable-decoder)

    if(NOT VCPKG_TARGET_IS_MINGW)
        list(APPEND OPTIONS --with-pic=yes)
    endif()

    vcpkg_make_configure(
        SOURCE_PATH "${SOURCE_PATH}"
        OPTIONS
            ${OPTIONS}
    )
    vcpkg_make_install()

    file(REMOVE_RECURSE
        "${CURRENT_PACKAGES_DIR}/debug/include"
        "${CURRENT_PACKAGES_DIR}/debug/share"
        "${CURRENT_PACKAGES_DIR}/share/${PORT}/doc"
        "${CURRENT_PACKAGES_DIR}/share/${PORT}/man1"
    )

endif()

# Catch regressions in the source build or the upstream installation recipe.
file(GLOB_RECURSE MPGLIB_ARTIFACTS
    "${CURRENT_PACKAGES_DIR}/*mpghip*"
    "${CURRENT_PACKAGES_DIR}/*mpglib*"
)
if(MPGLIB_ARTIFACTS)
    message(FATAL_ERROR "MPGLIB artifacts must not be packaged: ${MPGLIB_ARTIFACTS}")
endif()

# unofficial, but port legacy
file(COPY "${CMAKE_CURRENT_LIST_DIR}/mp3lame-config.cmake" DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")

vcpkg_install_copyright(FILE_LIST "${SOURCE_PATH}/COPYING")
