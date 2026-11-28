"""Pinned pre-relocation output baseline, with independent source-input detection."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ffbuild.versions import ROOT, generate_all


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class PortBaseline(unittest.TestCase):
    def test_unchanged_input_recipes_match_pre_relocation(self):
        fixture = json.loads((ROOT / "tests/fixtures/port-baseline.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generate_all(output=output, master=fixture["master_fixture"])
            unchanged = 0
            for name, row in fixture["versions"].items():
                if "inputs" not in row:
                    continue  # Seed changes when any dependency configuration changes.
                if not all((ROOT / p).is_file() and digest(ROOT / p) == h for p, h in row["inputs"].items()):
                    continue
                with self.subTest(port=name):
                    actual = {p.relative_to(output / name).as_posix(): digest(p)
                              for p in (output / name).rglob("*") if p.is_file()}
                    self.assertEqual(row["files"], actual)
                    unchanged += 1
            if not unchanged:
                self.skipTest("All baseline authored inputs have changed")
            self.assertFalse((output / "ffmpeg-deps").exists())
