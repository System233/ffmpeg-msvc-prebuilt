"""Differential archives, native PDB identity, and consumer SDK layout."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ffbuild import catalog
from ffbuild.identity import archive_name, variant_name
from ffbuild.state import PublishedState
from ffbuild.symbols import pe_identity, pdb_identity, verify_symbols, verify_debug_layout
from symbol_fixture import GUID, pe, pdb


class SymbolTests(unittest.TestCase):
    def test_guid_and_age_validation(self):
        self.assertEqual((GUID, 1), pe_identity(pe()))
        self.assertEqual((GUID, 1), pdb_identity(pdb()))
        b = {"bin/avcodec.dll": pe()}
        d = {"bin/avcodec.pdb": pdb()}
        verify_symbols(b, d, b.__getitem__, d.__getitem__)
        for invalid in (pdb(age=2), pdb(guid=b"x" * 16), b"bad"):
            with self.assertRaises(ValueError):
                verify_symbols(b, d, b.__getitem__, lambda n: invalid)
        with self.assertRaisesRegex(ValueError, "Missing DLL PDB"):
            verify_symbols(b, {}, b.__getitem__, d.__getitem__)
        with self.assertRaisesRegex(ValueError, "Unmatched"):
            verify_symbols({}, d, b.__getitem__, d.__getitem__)

    def test_debug_sdk_cannot_be_incomplete(self):
        b = ["bin/avcodec-62.dll", "lib/avcodec.lib"]
        d = ["debug/bin/avcodec-62.dll", "debug/lib/avcodec.lib"]
        verify_debug_layout(b, d)
        with self.assertRaisesRegex(ValueError, "Debug DLL set differs"):
            verify_debug_layout(b, [])
        with self.assertRaisesRegex(ValueError, "Missing Debug import library"):
            verify_debug_layout(b, d[:1])

    def test_debug_and_release_symbols_never_cross_match(self):
        b = {"bin/avcodec.dll": pe()}
        d = {"debug/bin/avcodec.dll": pe(guid=b"x"*16),
             "bin/avcodec.pdb": pdb(guid=b"x"*16),
             "debug/bin/avcodec.pdb": pdb()}
        with self.assertRaisesRegex(ValueError, "Unmatched"):
            verify_symbols(b, d, b.__getitem__, d.__getitem__)


class CatalogCompatibilityTests(unittest.TestCase):
    def test_historical_format_not_reused_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = {"version": "9.1", "triplet": "x64-windows", "linkage": "shared",
                   "license": "lgpl", "channel": "release", "release_date": "2026-11-25",
                   "expected_variants": 1}
            def assets(record, kind):
                return {k: {"file": archive_name(record, kind=k), "size": 1,
                            "digest": "sha256:" + "b"*64}
                        for k in ("binary", kind)}
            row["assets"] = assets(row, "develop")
            old = {"tag": "ffmpeg-9.1-r1", "date": "2026-11-25",
                   "variants": {"x64-windows-shared-lgpl": catalog._variant(row, "2026-11-25", native=False)}}
            catalog.write_json(root / "index.json", {"schema": 2, "releases": ["9.1"], "master": []})
            catalog.write_json(root / "releases/9.1.json", {"version": "9.1", "lts": False, "releases": [old]})
            self.assertIn("develop", old["variants"]["x64-windows-shared-lgpl"])
            self.assertIsNone(PublishedState(directory=root).find_abi(
                "9.1", "x64-windows", "a"*64))
            fresh = dict(row, package_format=2, abi_hash="a"*64, release_date="2026-11-26")
            fresh["assets"] = assets(fresh, "debug")
            catalog.register_release(root, [fresh])
            rows = catalog.load_shard(root, "releases", "9.1")["releases"]
            self.assertIn(old, rows)
            found = PublishedState(directory=root).find_abi("9.1", "x64-windows", "a"*64)
            self.assertEqual(fresh["assets"], found["assets"])
            bad = dict(fresh, assets=dict(fresh["assets"], develop=row["assets"]["develop"]))
            with self.assertRaisesRegex(ValueError, "asset set"):
                catalog.register_release(root, [bad])


@unittest.skipUnless(shutil.which("cmake") and shutil.which("ninja"), "CMake and Ninja needed")
class ConsumerLayoutTests(unittest.TestCase):
    def test_reconfigure_after_install_and_remove_addon(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prefix, src, build = root/"sdk", root/"src", root/"build"
            src.mkdir()
            for name in ("lib/avutil.lib", "include/libavutil/avutil.h", "bin/avutil-60.dll",
                         "lib/avcodec.lib", "include/libavcodec/avcodec.h", "bin/avcodec-62.dll"):
                path = prefix/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            template = (Path(__file__).resolve().parents[1] / "scripts/cmake/FindFFmpeg.cmake.in").read_text()
            values = {"FFMPEG_VERSION": "8.1.3", "LIBAVUTIL_VERSION": "60.0.0",
                      "LIBAVCODEC_VERSION": "62.0.0", "VCPKG_LIBRARY_LINKAGE": "dynamic"}
            import re
            module = re.sub(r"@([A-Za-z0-9_]+)@", lambda m: values.get(m[1], ""), template)
            (src/"FindFFmpeg.cmake").write_text(module)
            (src/"CMakeLists.txt").write_text("""
cmake_minimum_required(VERSION 3.21)
project(consumer LANGUAGES NONE)
set(WIN32 TRUE)
set(CMAKE_FIND_LIBRARY_PREFIXES "")
set(CMAKE_FIND_LIBRARY_SUFFIXES ".lib")
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}")
find_package(FFmpeg REQUIRED)
foreach(component avutil avcodec)
  get_target_property(loc FFmpeg::${component} IMPORTED_LOCATION_DEBUG)
  get_target_property(imp FFmpeg::${component} IMPORTED_IMPLIB_DEBUG)
  file(APPEND "${CMAKE_BINARY_DIR}/selected.txt" "${loc}|${imp}\n")
endforeach()
""")
            def configure(expected):
                output = build/"selected.txt"
                output.unlink(missing_ok=True)
                result = subprocess.run(["cmake", "-S", str(src), "-B", str(build), "-G",
                                         "Ninja Multi-Config", "-DFFMPEG_ROOT="+prefix.as_posix()],
                                        capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stdout+result.stderr)
                lines = output.read_text().splitlines()
                self.assertEqual(2, len(lines))
                for line in lines:
                    self.assertEqual(expected, "/debug/" in line, line)
            configure(False)
            for name in ("debug/bin/avutil-60.dll", "debug/lib/avutil.lib"):
                path = prefix/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"debug")
            configure(False)  # incomplete add-on cannot mix CRTs/modules
            for name in ("debug/bin/avcodec-62.dll", "debug/lib/avcodec.lib"):
                (prefix/name).write_bytes(b"debug")
            configure(True)
            (prefix/"debug/bin/avutil-60.dll").unlink()
            configure(False)
