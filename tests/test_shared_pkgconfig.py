"""Exercise the actual shared-only native Port pkg-config normalization."""

import re
import shutil
from cmake_blackbox_fixture import PKGCONF, run as run_command
import os
import shlex
import tempfile
import unittest
from pathlib import Path

from ffbuild.versions import ROOT


@unittest.skipUnless(shutil.which("cmake"), "CMake is required")
class SharedPkgConfigTests(unittest.TestCase):
    def normalize(self, root, linkage):
        recipe = (ROOT / "scripts/cmake/ffmpeg-portfile.cmake").read_text(encoding="utf-8")
        block = recipe.split("# BEGIN shared pkg-config normalization", 1)[1].split(
            "# END shared pkg-config normalization", 1)[0]
        script = root / "normalize.cmake"
        script.write_text("cmake_minimum_required(VERSION 3.20)\n" + block, encoding="utf-8")
        run_command(["cmake", f"-DCURRENT_PACKAGES_DIR={root.as_posix()}",
                        f"-DVCPKG_LIBRARY_LINKAGE={linkage}", "-P", str(script)],
                       check=True)

    def test_shared_release_and_debug_remove_only_private_link_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fields = ('prefix=${pcfiledir}/../..\nName: libavcodec\n'
                      'Version: 61.19.101\nRequires: \n'
                      'Requires.private: libavutil >= 59.39.100\n'
                      'Libs: "-L${prefix}/lib" -lavcodec\n'
                      'Libs.private: -lthird-party-static ' + chr(92) + '\n'
                      ' -lother-private\nCflags: "-I${prefix}/include"\n')
            expected = re.sub(r"Libs[.]private:[^\n]*\n -lother-private",
                              "Libs.private:", fields)
            release = root / "lib/pkgconfig/libavcodec.pc"
            debug = root / "debug/lib/pkgconfig/libavcodec.pc"
            for path in (release, debug):
                path.parent.mkdir(parents=True)
            release.write_bytes(fields.encode())
            debug.write_bytes(fields.replace("\n", "\r\n").encode())
            self.normalize(root, "dynamic")
            for path in (release, debug):
                self.assertEqual(expected, path.read_text(encoding="utf-8"))
            self.normalize(root, "dynamic")
            self.assertEqual(expected, release.read_text(encoding="utf-8"))

    def test_native_static_keeps_original_metadata_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / "lib/pkgconfig/libavcodec.pc",
                     root / "debug/lib/pkgconfig/libavcodec.pc"]
            original = b"Libs: -lavcodec\r\nLibs.private: -lthird-party-static\r\n"
            for path in paths:
                path.parent.mkdir(parents=True)
                path.write_bytes(original)
            self.normalize(root, "static")
            for path in paths:
                self.assertEqual(original, path.read_bytes())

    def test_shared_private_requires_filter_preserves_public_requirements_and_internal_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for cfg in ("", "debug"):
                folder = root / cfg / "lib/pkgconfig"
                folder.mkdir(parents=True)
                (folder / "libavutil.pc").write_text(
                    "Name: libavutil\nDescription: fixture\nVersion: 56.1.0\nLibs: -lavutil\n")
                (folder / "libavcodec.pc").write_text(
                    "Name: libavcodec\nDescription: fixture\nVersion: 58.1.0\n"
                    "Requires: public-api >= 2.0\n"
                    "Requires.private: libavutil >= 56.1.0, private-static >= 1.0\n"
                    "Libs: -lavcodec -lpublic-api\nLibs.private: -lprivate-static\n"
                    "Cflags: -DPUBLIC_HEADER=1\n")
            self.normalize(root, "dynamic")
            for cfg in ("", "debug"):
                with self.subTest(config=cfg or "Release"):
                    content = (root / cfg / "lib/pkgconfig/libavcodec.pc").read_text()
                    self.assertIn("Requires: public-api >= 2.0\n", content)
                    self.assertIn("Libs: -lavcodec -lpublic-api\n", content)
                    self.assertIn("Cflags: -DPUBLIC_HEADER=1\n", content)
                    self.assertRegex(content, r"(?m)^Requires[.]private:\s*libavutil\s*>=\s*56[.]1[.]0\s*$")
                    self.assertNotIn("private-static", content)

    def test_variable_path_flags_are_escaped_once_after_relocation(self):
        # vcpkg quotes variable-only flags. Native pkgconf 2.5.1 then
        # double-escapes expanded spaces, which FindPkgConfig splits.
        for linkage in ("dynamic", "static"):
            with self.subTest(linkage=linkage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "SDK with spaces"
                for cfg in ("", "debug"):
                    prefix = root / cfg
                    pc = prefix / "lib/pkgconfig"
                    pc.mkdir(parents=True)
                    (pc / "libavutil.pc").write_text(
                        'prefix=${pcfiledir}/../..\nlibdir=${prefix}/lib\n'
                        'includedir=${prefix}/include\nName: libavutil\nDescription: fixture\n'
                        'Version: 56.1.0\nLibs: "-L${libdir}" -lavutil\n'
                        'Cflags: "-I${includedir}" -DKEEP=1\n',
                        encoding="utf-8")
                recipe = (ROOT / "scripts/cmake/ffmpeg-portfile.cmake").read_text(encoding="utf-8")
                block = recipe.split("# BEGIN native pkg-config path normalization", 1)[1].split(
                    "# END native pkg-config path normalization", 1)[0]
                script = root / "normalize-paths.cmake"
                script.write_text("cmake_minimum_required(VERSION 3.21)\n" + block, encoding="utf-8")
                run_command(["cmake", f"-DCURRENT_PACKAGES_DIR={root.as_posix()}",
                             "-DVCPKG_TARGET_IS_WINDOWS=ON", f"-DVCPKG_LIBRARY_LINKAGE={linkage}",
                             "-P", script], check=True)
                for cfg in ("", "debug"):
                    prefix = root / cfg
                    env = dict(os.environ, PKG_CONFIG_PATH="", PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"))
                    env.pop("PKG_CONFIG_SYSROOT_DIR", None)
                    content = (prefix / "lib/pkgconfig/libavutil.pc").read_text()
                    self.assertIn("Libs: -L${libdir} -lavutil", content)
                    self.assertIn("Cflags: -I${includedir} -DKEEP=1", content)
                    if os.name != "nt":
                        continue
                    r = run_command([PKGCONF, "--cflags", "--libs", "libavutil"], env=env, check=True)
                    tokens = shlex.split(r.stdout)
                    self.assertIn("-L" + (prefix / "lib").as_posix(), tokens)
                    self.assertIn("-I" + (prefix / "include").as_posix(), tokens)
                    self.assertIn("-DKEEP=1", tokens)

    def test_shared_does_not_export_private_compile_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "lib/pkgconfig"
            folder.mkdir(parents=True)
            pc = folder / "libavutil.pc"
            original = ("Name: libavutil\nDescription: fixture\nVersion: 56.1.0\n"
                        "Libs: -lavutil\nCflags: -DPUBLIC=1\n"
                        "Cflags.private: -DPRIVATE=1 -Iprivate\n")
            pc.write_text(original)
            self.normalize(root, "static")
            self.assertEqual(original, pc.read_text())
            self.normalize(root, "dynamic")
            content = pc.read_text()
            self.assertIn("Cflags: -DPUBLIC=1", content)
            self.assertNotIn("-DPRIVATE=1", content)
            self.assertNotIn("-Iprivate", content)

    def test_public_archive_pkgconfig_validation_accepts_escaped_variable_paths(self):
        from ffbuild.sdk_validation import _CORE_MODULES, _verify_pkgconfig
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory) / "public sdk with spaces"
            (sdk / "include").mkdir(parents=True)
            for cfg in ("", "debug"):
                selected = sdk / cfg
                pc = selected / "lib/pkgconfig"
                pc.mkdir(parents=True)
                include = "${prefix}/../include" if cfg else "${prefix}/include"
                for module in _CORE_MODULES:
                    (pc / ("lib" + module + ".pc")).write_text(
                        'prefix=${pcfiledir}/../..\nlibdir=${prefix}/lib\n'
                        f'includedir={include}\nName: lib{module}\nDescription: fixture\n'
                        f'Version: 1.0\nLibs: -L${{libdir}} -l{module}\nCflags: -I${{includedir}}\n',
                        encoding="utf-8")
                _verify_pkgconfig(Path(PKGCONF), sdk, selected)
            # A correctly escaped but wrong directory is still rejected.
            pc = sdk / "lib/pkgconfig/libavcodec.pc"
            pc.write_text(pc.read_text().replace("includedir=${prefix}/include",
                                                 "includedir=${prefix}/wrong"))
            with self.assertRaisesRegex(ValueError, "Unexpected pkg-config includedir"):
                _verify_pkgconfig(Path(PKGCONF), sdk, sdk)

    def test_empty_and_absent_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "lib/pkgconfig"
            folder.mkdir(parents=True)
            empty = folder / "libavutil.pc"
            absent = folder / "libswscale.pc"
            empty.write_bytes(b"Libs.private:\nLibs: -lavutil\n")
            absent.write_bytes(b"Libs: -lswscale\n")
            self.normalize(root, "dynamic")
            self.assertEqual("Libs.private:\nLibs: -lavutil\n", empty.read_text())
            self.assertEqual("Libs: -lswscale\n", absent.read_text())


if __name__ == "__main__":
    unittest.main()
