"""Contract tests for the encoder-only LAME overlay and FFmpeg linker patches."""

import json
import unittest
from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]


class TestMp3lameOverlay(unittest.TestCase):
    def test_overlay_version_and_decoder_disable(self):
        port = ROOT / "ports/mp3lame"
        metadata = json.loads((port / "vcpkg.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["name"], "mp3lame")
        self.assertGreaterEqual(metadata["port-version"], 18)
        portfile = (port / "portfile.cmake").read_text(encoding="utf-8")
        self.assertIn("disable-mpglib.patch", portfile)
        self.assertIn("--disable-decoder", portfile)
        self.assertIn("MPGLIB_ARTIFACTS", portfile)

    def test_patch_disables_both_windows_build_types(self):
        patch = (ROOT / "ports/mp3lame/disable-mpglib.patch").read_text(
            encoding="utf-8",
        )
        self.assertEqual(patch.count("-      <PreprocessorDefinitions>"), 4)
        self.assertNotIn("+      <PreprocessorDefinitions>NDEBUG;_WINDOWS;HAVE_MPGLIB", patch)
        self.assertIn('-    <ProjectReference Include="vc11_mpglib.vcxproj">', patch)
        self.assertIn("-hip_decode_init", patch)
        self.assertIn("-lame_decode_init", patch)

    def test_no_ffmpeg_patch_links_mpglib(self):
        patch_files = list((ROOT / "patches").rglob("*.patch"))
        self.assertGreater(len(patch_files), 10)
        for filename in patch_files:
            with self.subTest(patch=str(filename.relative_to(ROOT))):
                self.assertNotIn(
                    "-llibmpghip-static", filename.read_text(encoding="utf-8")
                )

    def test_cmake_target_no_longer_links_decoder(self):
        config = (ROOT / "ports/mp3lame/mp3lame-config.cmake").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("mpghip", config)


if __name__ == "__main__":
    unittest.main()
