"""Exercise the actual shared-only native Port pkg-config normalization."""

import re
import shutil
import subprocess
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
        subprocess.run(["cmake", f"-DCURRENT_PACKAGES_DIR={root.as_posix()}",
                        f"-DVCPKG_LIBRARY_LINKAGE={linkage}", "-P", str(script)],
                       check=True, capture_output=True, text=True)

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
