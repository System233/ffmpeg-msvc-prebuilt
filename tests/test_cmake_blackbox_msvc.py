"""Native compiler/linker and DLL-loader contracts using a tiny real SDK."""
import os
import json
import re
import shlex
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from cmake_blackbox_fixture import ROOT, SDKFixture, TOOLS, PKGCONF, run, output

VCPKG_ROOT = os.environ.get('FFBUILD_TEST_VCPKG_ROOT') or os.environ.get('VCPKG_ROOT')
LIB_EXE = os.environ.get('FFBUILD_TEST_LIB_EXE')
DUMPBIN = Path(LIB_EXE).with_name('dumpbin.exe') if LIB_EXE else None


@unittest.skipUnless(os.name == "nt" and os.environ.get("FFBUILD_TEST_MSVC") == "1" and TOOLS,
                     "Opt-in VS 2022, CMake, Ninja and pkgconf test")
class NativeSDKContract(unittest.TestCase):
    generator = ("-G", "Visual Studio 17 2022", "-A", "x64")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ffmpeg-native-contract-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def checked(self, args, **kwargs):
        p = run(args, **kwargs)
        self.assertEqual(0, p.returncode, output(p))
        return p.stdout

    def assert_archive_runtime(self, archive, expected):
        self.assertIsNotNone(DUMPBIN, "Native contract runner must provide dumpbin.exe")
        text = self.checked([DUMPBIN, "/nologo", "/directives", archive])
        self.assertIn("RuntimeLibrary=" + expected, text, str(archive))

    def assert_static_crt_dlls(self, f):
        self.assertIsNotNone(DUMPBIN, "Native contract runner must provide dumpbin.exe")
        crt_import = re.compile(
            r"^(?:MSVCP|MSVCR|VCRUNTIME|UCRTBASE|API-MS-WIN-CRT|CONCRT)", re.IGNORECASE)
        for config in ("", "debug"):
            for module in f.modules:
                dll = f.sdk / config / "bin" / f.dll(module)
                text = self.checked([DUMPBIN, "/nologo", "/dependents", dll])
                imports = re.findall(r"^\s+([A-Za-z0-9_.-]+\.dll)\s*$", text,
                                     re.IGNORECASE | re.MULTILINE)
                dynamic_crt = [name for name in imports if crt_import.match(name)]
                self.assertEqual([], dynamic_crt,
                                 f"{dll} unexpectedly imports the dynamic MSVC/UCRT runtime")

    def produce(self, linkage, runtime="MultiThreaded", *, required_link_option=False, raw_private_metadata=False):
        f = SDKFixture(self.root, linkage)
        # The configure-only fixture creates empty archives. Remove them
        # before asking the native linker to produce real import libraries.
        for folder in (f.sdk, f.deps):
            for artifact in folder.rglob("*"):
                if artifact.is_file() and artifact.suffix in (".lib", ".dll"):
                    artifact.unlink()
        src = self.root / "producer"
        src.mkdir()
        kind = "SHARED" if linkage == "dynamic" else "STATIC"
        (src / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(producer CXX)
set(CMAKE_MSVC_RUNTIME_LIBRARY "${RUNTIME}$<$<CONFIG:Debug>:Debug>$<$<BOOL:${USE_DLL_CRT}>:DLL>")
add_library(third STATIC third.cpp)
set_target_properties(third PROPERTIES DEBUG_POSTFIX d)
add_library(second STATIC second.cpp)
add_library(avutil ${KIND} avutil.cpp)
add_library(avcodec ${KIND} avcodec.cpp)
add_library(avformat ${KIND} avformat.cpp)
target_link_libraries(avutil PRIVATE third ws2_32)
target_link_libraries(avcodec PRIVATE second avutil)
target_link_libraries(avformat PRIVATE avcodec avutil)
set(fixture_targets third second avutil avcodec avformat)
if(RAW_PRIVATE_METADATA)
  add_library(leaf STATIC leaf.cpp)
  set_target_properties(leaf PROPERTIES DEBUG_POSTFIX d)
  target_link_libraries(third PRIVATE leaf)
  list(APPEND fixture_targets leaf)
endif()
foreach(t IN LISTS fixture_targets)
  target_compile_definitions(${t} PRIVATE BUILD_ID=$<IF:$<CONFIG:Debug>,200,100>)
  if(t STREQUAL "third" OR t STREQUAL "second" OR t STREQUAL "leaf")
    set(base "${DEPS}")
  else()
    set(base "${SDK}")
  endif()
  set_target_properties(${t} PROPERTIES ARCHIVE_OUTPUT_DIRECTORY_RELEASE "${base}/lib"
    ARCHIVE_OUTPUT_DIRECTORY_DEBUG "${base}/debug/lib"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${base}/bin"
    RUNTIME_OUTPUT_DIRECTORY_DEBUG "${base}/debug/bin")
endforeach()
if(KIND STREQUAL "SHARED")
  foreach(t avutil avcodec avformat)
    set_target_properties(${t} PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS TRUE)
    if(t STREQUAL "avutil")
      set(major 56)
    else()
      set(major 58)
    endif()
    # DLL and import library deliberately have different basenames.
    set_target_properties(${t} PROPERTIES RUNTIME_OUTPUT_NAME "${t}-${major}"
      ARCHIVE_OUTPUT_NAME "${t}"
      PDB_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/symbols/Release"
      PDB_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}/symbols/Debug")
    target_link_options(${t} PRIVATE /DEBUG:FULL)
    target_compile_options(${t} PRIVATE /Z7)
  endforeach()
endif()
""", encoding="utf-8")
        sources = {
            "third": '#include <vector>\nextern "C" int third(){std::vector<int> v{BUILD_ID}; return v.at(0);}',
            "second": '#include <vector>\nextern "C" int second(){std::vector<int> v{BUILD_ID}; return v.at(0);}',
            "avutil": '#include <winsock2.h>\nextern "C" int third(); extern "C" int avutil_version(){WSASetLastError(0); return BUILD_ID+third()+WSAGetLastError();}',
            "avcodec": 'extern "C" int second(); extern "C" int avutil_version(); extern "C" int avcodec_version(){return BUILD_ID+second()+avutil_version();}',
            "avformat": 'extern "C" int avutil_version(); extern "C" int avcodec_version(); extern "C" int avformat_version(){return BUILD_ID+avcodec_version()+avutil_version();}',
        }
        if raw_private_metadata:
            # Actual archive closure: avformat -> avcodec -> avutil ->
            # third -> leaf. second is another private library of avcodec.
            sources["leaf"] = 'extern "C" int leaf(){return BUILD_ID;}'
            sources["third"] = (
                '#include <vector>\nextern "C" int leaf(); '
                'extern "C" int third(){std::vector<int> v{BUILD_ID}; '
                'return leaf()==v.at(0) ? v.at(0) : -999;}')
        if required_link_option:
            # The registration object is not otherwise referenced by the
            # application. A real /INCLUDE directive must pull it in.
            sources["third"] = (
                '#include <vector>\nstatic int registered=0; '
                'extern "C" void register_fixture(){registered=1;} '
                'extern "C" int third(){std::vector<int> v{BUILD_ID}; '
                'return registered ? v.at(0) : -999;}')
            sources["registration"] = (
                'extern "C" void register_fixture(); '
                'extern "C" {int fixture_marker=1;} '
                'struct Registration {Registration(){register_fixture();}}; '
                'static Registration registration;')
            with (src / "CMakeLists.txt").open("a", encoding="utf-8") as out:
                out.write("\ntarget_sources(third PRIVATE registration.cpp)\n")
            f.flags["avutil"] = tuple(flags + " -Wl,/INCLUDE:fixture_marker"
                                      for flags in f.flags["avutil"])
            f.write_pc()
        for name, content in sources.items():
            (src / (name + ".cpp")).write_text(content, encoding="utf-8")
        for name in f.modules:
            (f.sdk / "include" / ("lib" + name) / (name + ".h")).write_text(
                f'#ifdef __cplusplus\nextern "C" {{\n#endif\nint {name}_version(void);\n#ifdef __cplusplus\n}}\n#endif\n')
        pb = self.root / "producer-build"
        self.checked(["cmake", "-S", src, "-B", pb, *self.generator,
                      "-DSDK=" + f.sdk.as_posix(), "-DDEPS=" + f.deps.as_posix(),
                      "-DKIND=" + kind, "-DRUNTIME=MultiThreaded",
                      "-DRAW_PRIVATE_METADATA=" + ("ON" if raw_private_metadata else "OFF"),
                      "-DUSE_DLL_CRT=" + ("ON" if runtime.endswith("DLL") else "OFF")])
        for cfg in ("Release", "Debug"):
            self.checked(["cmake", "--build", pb, "--config", cfg, "--parallel", "2"])
        extra = ("-DVCPKG_CRT_LINKAGE=" + ("dynamic" if runtime.endswith("DLL") else "static"),)
        if raw_private_metadata:
            self.prepare_raw_private_metadata(f)
            extra += ("-DFFBUILD_TEST_NORMALIZE_SHARED=ON",)
        p = f.generate(extra=extra)
        self.assertEqual(0, p.returncode, output(p))
        if linkage == "static" and not raw_private_metadata:
            f.install_deps()
        return f

    def prepare_raw_private_metadata(self, f):
        """Native FFmpeg-style metadata, transformed by the pinned vcpkg helper."""
        self.assertTrue(VCPKG_ROOT, "Pinned vcpkg checkout required")
        for cfg, suffix in (("", ""), ("debug", "d")):
            folder = f.deps / cfg / "lib/pkgconfig"
            folder.mkdir(parents=True)
            for package, archive, requires in (("fixture-third", "third" + suffix, "fixture-leaf >= 1.0"),
                                               ("fixture-leaf", "leaf" + suffix, "")):
                (folder / (package + ".pc")).write_text(
                    "prefix=${pcfiledir}/../..\nName: " + package +
                    "\nDescription: private static archive\nVersion: 1.0\n"
                    "Requires: " + requires + "\nLibs: -L${prefix}/lib -l" + archive + "\n",
                    encoding="utf-8")
            for module, version in f.modules.items():
                prefix = f.sdk / cfg
                requires = ["lib" + dep for dep in f.graph[module]]
                private_libs = ""
                if module == "avutil":
                    requires.append("fixture-third >= 1.0")
                    private_libs = "-lws2_32"
                if module == "avcodec":
                    private_libs = "-lsecond"
                (prefix / "lib/pkgconfig" / ("lib" + module + ".pc")).write_text(
                    f"prefix={prefix.as_posix()}\nlibdir=${{prefix}}/lib\nincludedir=${{prefix}}/include\n"
                    f"Name: lib{module}\nDescription: native raw metadata\nVersion: {version}\n"
                    f"Requires.private: {' '.join(requires)}\n"
                    f"Libs: -L${{libdir}} -l{module}\nLibs.private: {private_libs}\n"
                    "Cflags: -I${includedir}\n", encoding="utf-8")
        script = self.root / "native-pc-fixup.cmake"
        helper = Path(VCPKG_ROOT) / "scripts/cmake"
        script.write_text(
            "cmake_minimum_required(VERSION 3.21)\n"
            "set(VCPKG_HOST_IS_WINDOWS TRUE)\n"
            "function(debug_message)\nendfunction()\n"
            + "".join(f'include("{(helper / name).as_posix()}")\n' for name in
                      ("vcpkg_list.cmake", "z_vcpkg_function_arguments.cmake", "vcpkg_fixup_pkgconfig.cmake"))
            # Package existence is checked below with pkgconf against the
            # actual installed metadata and again after relocation/removal.
            + "vcpkg_fixup_pkgconfig(SKIP_CHECK)\n",
            encoding="utf-8")
        self.checked(["cmake", "-DCURRENT_PACKAGES_DIR=" + f.sdk.as_posix(),
                      "-DCURRENT_INSTALLED_DIR=" + f.deps.as_posix(),
                      "-DVCPKG_LIBRARY_LINKAGE=" + f.linkage, "-P", script])

    def consumer(self, f, runtime="MultiThreaded"):
        # Runtime values are deliberately derived from the fixture's independent
        # constants. Every call crosses a real dependency edge.
        (f.src / "main.cpp").write_text(r"""
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/avutil.h>
#include <vector>
#include <cstdlib>
#include <cwchar>
#if defined(_MSC_VER)
#ifndef _MT
#error "Expected an MSVC multithreaded CRT"
#endif
#if EXPECT_DEBUG_CRT
#ifndef _DEBUG
#error "Expected Debug CRT"
#endif
#else
#ifdef _DEBUG
#error "Expected Release CRT"
#endif
#endif
#if EXPECT_DLL_CRT
#ifndef _DLL
#error "Expected the consumer's dynamic CRT selection to be preserved"
#endif
#else
#ifdef _DLL
#error "Expected the consumer's static CRT selection to be preserved"
#endif
#endif
#endif
#ifdef SHARED_SDK
#include <windows.h>
#include <filesystem>
#include <iostream>
#endif
int wmain(int argc, wchar_t** argv) {
  if(argc<2) return 10;
  std::vector<int> v{static_cast<int>(std::wcstol(argv[1], nullptr, 10))};
  const int n=v.at(0);
  if(avutil_version()!=2*n || avcodec_version()!=4*n || avformat_version()!=7*n) return 11;
#ifdef SHARED_SDK
  if(argc!=3) return 12;
  for(auto dll : {L"avutil-56.dll", L"avcodec-58.dll", L"avformat-58.dll"}) {
    wchar_t path[32768];
    auto module=GetModuleHandleW(dll);
    if(!module || !GetModuleFileNameW(module,path,32768)) return 13;
    auto expected=std::filesystem::path(argv[2])/dll;
    if(!std::filesystem::equivalent(path,expected)) {
      std::wcerr << L"Unexpected DLL: " << path << L" expected " << expected.c_str();
      return 14;
    }
  }
#endif
  return 0;
}
""")
        (f.src / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(consumer CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_MSVC_RUNTIME_LIBRARY "${RUNTIME}$<$<CONFIG:Debug>:Debug>$<$<BOOL:${USE_DLL_CRT}>:DLL>")
find_package(FFmpeg CONFIG REQUIRED)
list(APPEND CMAKE_MODULE_PATH "${FFmpeg_DIR}")
find_package(FFmpeg MODULE REQUIRED)
set(_expected_runtime "${RUNTIME}$<$<CONFIG:Debug>:Debug>$<$<BOOL:${USE_DLL_CRT}>:DLL>")
foreach(mode full demand legacy alias)
  add_executable(check-${mode} main.cpp)
  get_target_property(_actual_runtime check-${mode} MSVC_RUNTIME_LIBRARY)
  if(NOT "${_actual_runtime}" STREQUAL "${_expected_runtime}")
    message(FATAL_ERROR "FindFFmpeg changed consumer CRT for check-${mode}: ${_actual_runtime}")
  endif()
  file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/runtime-${mode}-$<CONFIG>.txt"
       CONTENT "$<TARGET_GENEX_EVAL:check-${mode},$<TARGET_PROPERTY:check-${mode},MSVC_RUNTIME_LIBRARY>>")
  target_compile_definitions(check-${mode} PRIVATE EXPECT_DLL_CRT=$<BOOL:${USE_DLL_CRT}> EXPECT_DEBUG_CRT=$<CONFIG:Debug>)
  if(SHARED_SDK)
    target_compile_definitions(check-${mode} PRIVATE SHARED_SDK)
  endif()
  set_target_properties(check-${mode} PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/$<CONFIG>/${mode}")
endforeach()
target_link_libraries(check-full PRIVATE FFmpeg::FFmpeg)
target_link_libraries(check-demand PRIVATE FFmpeg::avformat)
target_link_libraries(check-alias PRIVATE FFMPEG::avformat)
target_include_directories(check-legacy PRIVATE ${FFMPEG_INCLUDE_DIRS})
target_link_libraries(check-legacy PRIVATE ${FFMPEG_LIBRARIES})
if(SHARED_SDK)
  foreach(mode full demand alias)
    add_custom_command(TARGET check-${mode} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_RUNTIME_DLLS:check-${mode}>
        "$<TARGET_FILE_DIR:check-${mode}>" COMMAND_EXPAND_LISTS)
  endforeach()
  install(TARGETS check-full RUNTIME DESTINATION bin)
  install(FILES $<TARGET_RUNTIME_DLLS:check-full> DESTINATION bin)
endif()
""")
        args = ["cmake", "-S", f.src, "-B", f.build, *self.generator,
                "-DCMAKE_PREFIX_PATH=" + f.sdk.as_posix(),
                "-DRUNTIME=MultiThreaded", "-DUSE_DLL_CRT=" + ("ON" if runtime.endswith("DLL") else "OFF"), "-DSHARED_SDK=" + ("ON" if f.linkage == "dynamic" else "OFF")]
        self.checked(args)
        return args

    def check_runtime(self, f, cfg, sdk_config, consumer_crt="MultiThreaded"):
        self.checked(["cmake", "--build", f.build, "--config", cfg, "--parallel", "2", "--clean-first"])
        prefix = f.sdk / ("debug" if sdk_config == "Debug" else "")
        expected = "200" if sdk_config == "Debug" else "100"
        expected_runtime = "MultiThreaded" + ("Debug" if cfg == "Debug" else "")
        if consumer_crt == "MultiThreadedDLL":
            expected_runtime += "DLL"
        windows = Path(os.environ["SystemRoot"])
        base_env = dict(os.environ, PATH=os.pathsep.join(str(p) for p in (windows / "System32", windows)))
        for mode in ("full", "demand", "legacy", "alias"):
            out = f.build / cfg / mode
            runtime_file = f.build / f"runtime-{mode}-{cfg}.txt"
            self.assertEqual(expected_runtime, runtime_file.read_text(encoding="utf-8").strip(),
                             f"Unexpected consumer runtime for {mode}/{cfg}")
            env = base_env.copy()
            if f.linkage == "dynamic":
                if mode == "legacy":
                    env["PATH"] = str(prefix / "bin") + os.pathsep + env["PATH"]
                else:
                    for m in f.modules:
                        dll = f.dll(m)
                        self.assertEqual((prefix / "bin" / dll).read_bytes(), (out / dll).read_bytes())
            args = [out / f"check-{mode}.exe", expected]
            if f.linkage == "dynamic":
                # Opposite-configuration PATH must not override deployed DLLs.
                opposite = f.sdk / ("" if sdk_config == "Debug" else "debug") / "bin"
                if opposite.is_dir():
                    env["PATH"] += os.pathsep + str(opposite)
                args.append(prefix / "bin" if mode == "legacy" else out)
            self.checked(args, env=env, cwd=out)
        if f.linkage == "dynamic":
            dest = self.root / "install"
            shutil.rmtree(dest, ignore_errors=True)
            self.checked(["cmake", "--install", f.build, "--config", cfg, "--prefix", dest])
            for m in f.modules:
                self.assertEqual((prefix / "bin" / f.dll(m)).read_bytes(),
                                 (dest / "bin" / f.dll(m)).read_bytes())
            self.checked([dest / "bin/check-full.exe", expected, dest / "bin"], env=base_env, cwd=dest / "bin")

    def test_shared_binary_overlay_and_removal_runtime(self):
        f = self.produce("dynamic")
        self.assert_static_crt_dlls(f)
        binary = self.root / "fixture-binary.zip"
        debug = self.root / "fixture-debug.zip"
        from ffbuild.package import _files, _archive
        copyright_file = self.root / "fixture-copyright"
        copyright_file.write_text("test fixture")
        _archive(binary, _files(f.sdk, "shared", kind="binary"), copyright_file)
        _archive(debug, _files(f.sdk, "shared", kind="debug"), copyright_file)
        with zipfile.ZipFile(binary) as archive:
            self.assertNotIn("debug/lib/avutil.lib", archive.namelist())
        with zipfile.ZipFile(debug) as archive:
            self.assertNotIn("lib/avutil.lib", archive.namelist())
        shutil.rmtree(f.deps)  # No build-machine private archives are available.
        # Consume only extracted files; the original package is removed.
        shutil.rmtree(f.sdk)
        f.sdk = self.root / "extracted sdk"
        f.sdk.mkdir()
        with zipfile.ZipFile(binary) as archive:
            archive.extractall(f.sdk)
        # The shared DLL SDK is independent of the application's CRT. Exercise
        # /MT, /MTd, /MD and /MDd while the package contains only Release files.
        for consumer_crt in ("MultiThreaded", "MultiThreadedDLL"):
            args = self.consumer(f, consumer_crt)
            for cfg in ("Release", "Debug"):
                self.check_runtime(f, cfg, "Release", consumer_crt)
        with zipfile.ZipFile(debug) as archive:
            archive.extractall(f.sdk)
        for consumer_crt in ("MultiThreaded", "MultiThreadedDLL"):
            args = self.consumer(f, consumer_crt)
            for cfg in ("Release", "Debug"):
                self.check_runtime(f, cfg, cfg, consumer_crt)
        # Negative runtime control: same filename, wrong actual build.
        deployed = f.build / "Debug/full" / f.dll("avutil")
        shutil.copyfile(f.sdk / "bin" / f.dll("avutil"), deployed)
        mismatch = run([f.build / "Debug/full/check-full.exe", "200", deployed.parent], cwd=deployed.parent,
                       env=dict(os.environ, PATH=str(Path(os.environ["SystemRoot"]) / "System32")))
        self.assertEqual(11, mismatch.returncode, "Runtime oracle failed to detect Release DLL in Debug")
        # The same build directory must stop deploying Debug after removal.
        shutil.rmtree(f.sdk / "debug")
        self.checked(args)
        self.check_runtime(f, "Debug", "Release", "MultiThreadedDLL")

    def check_private_pkgconfig_consumer(self, f, config, *, static):
        folder = "debug" if config == "Debug" else ""
        prefix = f.sdk / folder
        env = dict(os.environ, PKG_CONFIG_PATH="", PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"))
        env.pop("PKG_CONFIG_SYSROOT_DIR", None)
        expected_names = {"avformat", "avcodec", "avutil"}
        private_names = {"second", "ws2_32", "third", "thirdd", "leaf", "leafd"}
        if static:
            suffix = "d" if config == "Debug" else ""
            expected_names |= {"second", "ws2_32", "third" + suffix, "leaf" + suffix}
        for flags in ([], ["--static"]):
            with self.subTest(config=config, pkgconf_flags=flags):
                text = self.checked([PKGCONF, *flags, "--cflags", "--libs", "libavformat"], env=env)
                names = {token[2:] for token in shlex.split(text) if token.startswith("-l")}
                if static or flags:
                    self.assertTrue(expected_names <= names, text)
                else:
                    self.assertIn("avformat", names)
                self.assertFalse((private_names - expected_names) & names, text)
        src = self.root / "pc-native-consumer"
        src.mkdir(exist_ok=True)
        (src / "main.cpp").write_text(
            '#include <libavformat/avformat.h>\nint main(){return avformat_version()==7*EXPECTED ? 0 : 1;}\n',
            encoding="utf-8")
        (src / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(pc_native_consumer CXX)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
set(PKG_CONFIG_USE_CMAKE_PREFIX_PATH FALSE)
find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED IMPORTED_TARGET libavformat)
add_executable(pc-consumer main.cpp)
target_compile_definitions(pc-consumer PRIVATE EXPECTED=$<IF:$<CONFIG:Debug>,200,100>)
target_link_libraries(pc-consumer PRIVATE PkgConfig::FFMPEG)
""", encoding="utf-8")
        build = self.root / ("pc-native-build-" + config)
        self.checked(["cmake", "-S", src, "-B", build, *self.generator,
                      "-DPKG_CONFIG_EXECUTABLE=" + Path(PKGCONF).as_posix(), "-DPKG_CONFIG_ARGN="], env=env)
        self.checked(["cmake", "--build", build, "--config", config, "--parallel", "2"], env=env)
        windows = Path(os.environ["SystemRoot"])
        runtime_env = dict(os.environ, PATH=os.pathsep.join(map(str, (prefix / "bin", windows / "System32", windows))))
        self.checked([build / config / "pc-consumer.exe"], env=runtime_env, cwd=build / config)

    def test_static_local_install_preserves_real_private_archive_closure(self):
        f = self.produce("static", raw_private_metadata=True)
        # vcpkg installs the FFmpeg package alongside its dependency packages.
        # Do not use the producer's build tree, a static ZIP, or manual
        # target_link_libraries calls for private archives.
        shutil.copytree(f.sdk, f.deps, dirs_exist_ok=True)
        shutil.rmtree(f.sdk)
        f.sdk = self.root / "relocated local static install"
        f.deps.rename(f.sdk)
        shutil.rmtree(self.root / "producer-build")
        self.consumer(f)
        for config in ("Release", "Debug"):
            with self.subTest(config=config, interface="CMake"):
                self.check_runtime(f, config, config)
            with self.subTest(config=config, interface="PkgConfig"):
                self.check_private_pkgconfig_consumer(f, config, static=True)
        # Remove the transitive leaf, not a directly linked FFmpeg module.
        # Both configurations were runnable before the mutation.
        (f.sdk / "debug/lib/leafd.lib").unlink()
        result = run(["cmake", "-S", f.src, "-B", f.build, *self.generator,
                      "-DCMAKE_PREFIX_PATH=" + f.sdk.as_posix()])
        self.assertNotEqual(0, result.returncode, output(result))
        self.assertIn("leafd.lib", output(result))

    def test_shared_private_archive_graph_is_consumable_without_private_packages(self):
        f = self.produce("dynamic", raw_private_metadata=True)
        # Ensure we cannot accidentally find any private archives or .pc
        # files on the producer side. The installed DLLs contain their code.
        shutil.rmtree(f.deps)
        shutil.rmtree(self.root / "producer-build")
        moved = self.root / "relocated public shared sdk"
        f.sdk.rename(moved)
        f.sdk = moved
        self.consumer(f, "MultiThreadedDLL")
        for config in ("Release", "Debug"):
            with self.subTest(config=config, interface="CMake"):
                self.check_runtime(f, config, config, "MultiThreadedDLL")
            with self.subTest(config=config, interface="PkgConfig"):
                self.check_private_pkgconfig_consumer(f, config, static=False)

    def test_static_mt_internal_graph_and_wrong_configuration_archive_rejected(self):
        f = self.produce("static")
        for archive in ("third.lib", "second.lib"):
            self.assert_archive_runtime(f.sdk / "lib" / archive, "MT_StaticRelease")
        for archive in ("thirdd.lib", "second.lib"):
            self.assert_archive_runtime(f.sdk / "debug/lib" / archive, "MTd_StaticDebug")
        self.consumer(f)
        for cfg in ("Release", "Debug"):
            self.check_runtime(f, cfg, cfg)
        # A Release /MT archive must not be accepted as the Debug /MTd dependency.
        shutil.copyfile(f.sdk / "lib/third.lib", f.sdk / "debug/lib/thirdd.lib")
        result = run(["cmake", "--build", f.build, "--config", "Debug", "--target", "check-demand", "--clean-first"])
        self.assertNotEqual(0, result.returncode, output(result))
        self.assertIn("LNK2038", output(result))

    def test_static_dynamic_crt_triplet_internal_graph_and_wrong_configuration_archive_rejected(self):
        # Alternate vcpkg triplet contract only. This controls the CRT used by
        # FFmpeg and its static dependencies; it does not describe consumer CRT.
        f = self.produce("static", "MultiThreadedDLL")
        self.consumer(f, "MultiThreadedDLL")
        for cfg in ("Release", "Debug"):
            self.check_runtime(f, cfg, cfg, "MultiThreadedDLL")
        shutil.copyfile(f.sdk / "debug/lib/thirdd.lib", f.sdk / "lib/third.lib")
        result = run(["cmake", "--build", f.build, "--config", "Release", "--target", "check-demand", "--clean-first"])
        self.assertNotEqual(0, result.returncode, output(result))
        self.assertIn("LNK2038", output(result))

    def test_required_linker_option_preserves_registration_object(self):
        f = self.produce("static", required_link_option=True)
        args = self.consumer(f)
        cmakelists = f.src / "CMakeLists.txt"
        original = cmakelists.read_text()
        # Positive control proves that the fixture and linker option really
        # work. The SDK itself must then deliver the same behavior unaided.
        cmakelists.write_text(original + "\nforeach(mode full demand legacy alias)\n"
            "  target_link_options(check-${mode} PRIVATE /INCLUDE:fixture_marker)\n"
            "endforeach()\n")
        self.checked(args)
        self.check_runtime(f, "Release", "Release")
        cmakelists.write_text(original)
        self.checked(args)
        self.check_runtime(f, "Release", "Release")

    def test_native_tester_cannot_silently_link_release_for_debug(self):
        # Configure the actual authored Native Tester, not a test copy.
        # CMake File API codemodel exposes the generated native link command.
        f = SDKFixture(self.root, "dynamic")
        for name, version in (("avdevice", "58.1.0"), ("avfilter", "7.1.0"),
                              ("swresample", "3.1.0"), ("swscale", "5.1.0")):
            f.modules[name] = version
            f.graph[name] = ("avutil",)
            f.flags[name] = ("", "")
            f.touch(f.sdk / "include" / ("lib" + name) / (name + ".h"))
            for cfg in ("", "debug"):
                f.touch(f.sdk / cfg / "lib" / (name + ".lib"))
                f.touch(f.sdk / cfg / "bin" / f.dll(name))
        f.write_pc()
        p = f.generate()
        self.assertEqual(0, p.returncode, output(p))
        query = f.build / ".cmake/api/v1/query/codemodel-v2"
        f.touch(query)
        args = ["cmake", "-S", ROOT / "ports/ffmpeg-tester", "-B", f.build, *self.generator,
                "-DCMAKE_PREFIX_PATH=" + f.sdk.as_posix(),
                "-DCMAKE_MODULE_PATH=" + (f.sdk / "share/ffmpeg").as_posix(),
                "-DVCPKG_TARGET_TRIPLET=x64-windows"]
        self.checked(args)

        def assert_debug_link():
            reply = f.build / ".cmake/api/v1/reply"
            model = json.loads(next(reply.glob("codemodel-v2-*.json")).read_text(encoding="utf-8"))
            debug = next(c for c in model["configurations"] if c["name"] == "Debug")
            target = next(t for t in debug["targets"] if t["name"] == "check-avutil")
            data = json.loads((reply / target["jsonFile"]).read_text(encoding="utf-8"))
            link = " ".join(x["fragment"] for x in data["link"]["commandFragments"])
            self.assertIn("/debug/lib/avutil.lib", link.replace(chr(92), "/").lower(),
                          "Native Tester Debug selects Release instead of Debug")

        assert_debug_link()
        (f.sdk / "debug/bin" / f.dll("avcodec")).unlink()
        p = run(args)
        if p.returncode:
            self.assertRegex(output(p), r"(?is)(debug|avcodec|configuration)")
        else:
            assert_debug_link()


    @unittest.skipUnless(VCPKG_ROOT and (Path(VCPKG_ROOT) / "scripts/buildsystems/vcpkg.cmake").is_file(),
                         "Pinned vcpkg checkout required")
    def test_real_vcpkg_wrapper_native_consumer(self):
        f = self.produce("static")
        install = self.root / "vcpkg-installed"
        install.mkdir()
        target = install / "x64-windows"
        f.sdk.rename(target)
        f.sdk = target
        shutil.copy2(ROOT / "scripts/cmake/vcpkg-cmake-wrapper.cmake", target / "share/ffmpeg")
        args = self.consumer(f)
        # Reconfigure a fresh consumer with the actual pinned toolchain and
        # without CMAKE_PREFIX_PATH or manual module path on the command line.
        shutil.rmtree(f.build)
        cmakelists = f.src / "CMakeLists.txt"
        text = cmakelists.read_text()
        # Keep a nonempty sentinel so CMake's undefined-vs-empty variable
        # semantics cannot masquerade as a wrapper search-state regression.
        text = text.replace("find_package(FFmpeg CONFIG REQUIRED)",
                            'set(CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/sentinel")\n'
                            'set(_module_path_before "${CMAKE_MODULE_PATH}")\n'
                            'find_package(FFmpeg CONFIG REQUIRED)')
        text = text.replace('list(APPEND CMAKE_MODULE_PATH "${FFmpeg_DIR}")', r'''
if(NOT z_vcpkg_using_vcpkg_find_ffmpeg)
  message(FATAL_ERROR "The actual vcpkg wrapper was not used")
endif()
if(NOT "${CMAKE_MODULE_PATH}" STREQUAL "${_module_path_before}")
  message(FATAL_ERROR "Config wrapper changed module path: ${CMAKE_MODULE_PATH}")
endif()
''')
        text = text.replace("find_package(FFmpeg MODULE REQUIRED)", r'''
find_package(FFmpeg MODULE REQUIRED)
if(NOT z_vcpkg_using_vcpkg_find_ffmpeg)
  message(FATAL_ERROR "The actual vcpkg Module wrapper was not used")
endif()
if(NOT "${CMAKE_MODULE_PATH}" STREQUAL "${_module_path_before}")
  message(FATAL_ERROR "Module wrapper changed module path: ${CMAKE_MODULE_PATH}")
endif()
''')
        cmakelists.write_text(text)
        args = [a for a in args if not str(a).startswith("-DCMAKE_PREFIX_PATH=")]
        self.checked(args + ["-DCMAKE_TOOLCHAIN_FILE=" + (Path(VCPKG_ROOT) / "scripts/buildsystems/vcpkg.cmake").as_posix(),
                             "-DVCPKG_INSTALLED_DIR=" + install.as_posix(),
                             "-DVCPKG_TARGET_TRIPLET=x64-windows",
                             "-DVCPKG_MANIFEST_MODE=OFF",
                             "-DVCPKG_APPLOCAL_DEPS=OFF"])
        for cfg in ("Release", "Debug"):
            self.check_runtime(f, cfg, cfg)

    @unittest.skipUnless(VCPKG_ROOT and DUMPBIN and DUMPBIN.is_file(),
                         "Pinned vcpkg checkout and FFBUILD_TEST_LIB_EXE required")
    def test_real_pdb_copy_and_archive_identity(self):
        from ffbuild.package import _files, _archive
        from ffbuild.symbols import pe_identity, pdb_identity, verify_symbols, verify_debug_layout
        f = self.produce("dynamic")
        script = self.root / "copy-pdbs.cmake"
        helper = Path(VCPKG_ROOT) / "scripts/cmake/vcpkg_copy_pdbs.cmake"
        script.write_text(
            'cmake_minimum_required(VERSION 3.21)\n'
            f'set(CURRENT_PACKAGES_DIR "{f.sdk.as_posix()}")\n'
            'set(VCPKG_TARGET_IS_WINDOWS TRUE)\nset(VCPKG_LIBRARY_LINKAGE dynamic)\n'
            f'include("{helper.as_posix()}")\nvcpkg_copy_pdbs()\n')
        env = dict(os.environ, PATH=str(DUMPBIN.parent) + os.pathsep + os.environ["PATH"])
        self.checked(["cmake", "-P", script], env=env)
        for cfg in ("", "debug"):
            folder = f.sdk / cfg / "bin"
            for module in f.modules:
                dll = folder / f.dll(module)
                pdbs = list(folder.glob("*.pdb"))
                identity = pe_identity(dll.read_bytes())
                self.assertIsNotNone(identity)
                self.assertEqual(1, sum(pdb_identity(p.read_bytes()) == identity for p in pdbs))
        binary, debug = self.root / "binary.zip", self.root / "debug.zip"
        copyright_file = self.root / "copyright"
        copyright_file.write_text("fixture")
        _archive(binary, _files(f.sdk, "shared", kind="binary"), copyright_file)
        _archive(debug, _files(f.sdk, "shared", kind="debug"), copyright_file)
        with zipfile.ZipFile(binary) as rel, zipfile.ZipFile(debug) as dbg:
            verify_debug_layout(rel.namelist(), dbg.namelist())
            verify_symbols(rel.namelist(), dbg.namelist(), rel.read, dbg.read)
            self.assertFalse(any(n.endswith(".pdb") for n in rel.namelist()))
            # Same-named PDB from the opposite configuration is invalid.
            candidates = [n for n in dbg.namelist() if n.startswith("debug/bin/") and n.endswith(".pdb")]
            self.assertTrue(candidates)
            name = candidates[0]
            opposite = name.removeprefix("debug/")
            self.assertIn(opposite, dbg.namelist())
            with self.assertRaises(ValueError):
                verify_symbols(rel.namelist(), dbg.namelist(), rel.read,
                               lambda n: dbg.read(opposite if n == name else n))
