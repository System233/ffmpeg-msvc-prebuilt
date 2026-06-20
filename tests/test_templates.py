"""Tests for scripts/ffport/templates.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ffport"))
from templates import generate_portfile


class TestGeneratePortfile(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.port_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def read_portfile(self) -> str:
        pf = self.port_dir / "portfile.cmake"
        return pf.read_text()

    def test_basic_generation(self):
        generate_portfile(
            version="8.1.1",
            sha512="abc123",
            build={},
            patch_names=[],
            port_dir=self.port_dir,
            revision=2,
        )
        content = self.read_portfile()
        self.assertIn('set(FFMPEG_VERSION "8.1.1")', content)
        self.assertIn("set(FFMPEG_SHA512 abc123)", content)
        self.assertIn("set(FFMPEG_PORT_REVISION 2)", content)
        self.assertNotIn("FFMPEG_NEED_BIN2C", content)

    def test_cmake_defines(self):
        generate_portfile(
            version="8.1.1",
            sha512="abc123",
            build={
                "cmake_defines": {
                    "FFMPEG_NEED_BIN2C": "ON",
                    "FFMPEG_USE_CUSTOM_LD": "/usr/bin/ld",
                }
            },
            patch_names=[],
            port_dir=self.port_dir,
        )
        content = self.read_portfile()
        self.assertIn("set(FFMPEG_NEED_BIN2C ON)", content)
        self.assertIn('set(FFMPEG_USE_CUSTOM_LD /usr/bin/ld)', content)

    def test_cmake_defines_with_base_opts(self):
        generate_portfile(
            version="7.1",
            sha512="def456",
            build={
                "base_options": "--enable-gpl",
                "cmake_defines": {
                    "FFMPEG_SKIP_FEATURE_X": "TRUE",
                },
            },
            patch_names=[],
            port_dir=self.port_dir,
        )
        content = self.read_portfile()
        self.assertIn('set(FFMPEG_BASE_OPTIONS "--enable-gpl")', content)
        self.assertIn("set(FFMPEG_SKIP_FEATURE_X TRUE)", content)

    def test_cmake_defines_empty(self):
        generate_portfile(
            version="6.1.1",
            sha512="ghi789",
            build={"cmake_defines": {}},
            patch_names=[],
            port_dir=self.port_dir,
        )
        content = self.read_portfile()
        self.assertNotIn("FFMPEG_NEED_BIN2C", content)
        self.assertIn('set(FFMPEG_VERSION "6.1.1")', content)

    def test_no_cmake_defines_field(self):
        generate_portfile(
            version="5.1.2",
            sha512="xyz",
            build={},
            patch_names=[],
            port_dir=self.port_dir,
        )
        content = self.read_portfile()
        self.assertNotIn("cmake_defines", content)

    def test_revision_passthrough(self):
        generate_portfile(
            version="8.1.1",
            sha512="abc",
            build={},
            patch_names=[],
            port_dir=self.port_dir,
            revision=5,
        )
        content = self.read_portfile()
        self.assertIn("set(FFMPEG_PORT_REVISION 5)", content)

    def test_source_ref_emitted(self):
        generate_portfile(
            version="8.1.1",
            sha512="abc",
            build={},
            patch_names=[],
            port_dir=self.port_dir,
            revision=0,
            source={"ref": "n8.1.1-custom"},
        )
        content = self.read_portfile()
        self.assertIn('set(FFMPEG_REF "n8.1.1-custom")', content)


if __name__ == "__main__":
    unittest.main()
