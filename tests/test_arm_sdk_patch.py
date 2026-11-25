"""Regression against the original ARM vcvarsall Windows SDK patch.

Source: original CI change c80f908 / last pre-refactor build-release.yml.
Only the arm-windows triplet requires this workaround.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ffbuild.builder import patch_arm_sdk
from ffbuild.ci import main as ci_main


class ArmSdkPatchTests(unittest.TestCase):
    @staticmethod
    def installation(directory: Path, value: bytes) -> Path:
        script = directory / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
        script.parent.mkdir(parents=True)
        script.write_bytes(value)
        return script

    def test_original_blank_assignment_is_pinned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.installation(
                root, b"@echo off\r\nset __VCVARSALL_WINSDK=\r\nset OTHER=ok\r\n")
            with patch("ffbuild.builder.subprocess.run", return_value=SimpleNamespace(
                stdout=str(root) + "\n")):
                patch_arm_sdk()
            self.assertEqual(
                script.read_bytes(),
                b"@echo off\r\nset __VCVARSALL_WINSDK=10.0.22621.0\r\nset OTHER=ok\r\n")

    def test_existing_sdk_is_replaced_and_second_call_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.installation(
                root, b"set __VCVARSALL_WINSDK=10.0.19041.0\r\n")
            with patch("ffbuild.builder.subprocess.run", return_value=SimpleNamespace(
                stdout=str(root) + "\n")):
                patch_arm_sdk()
                first = script.read_bytes()
                patch_arm_sdk()
                self.assertEqual(first, script.read_bytes())
            self.assertEqual(first, b"set __VCVARSALL_WINSDK=10.0.22621.0\r\n")

    def test_path_not_found_reports_path_problem(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("ffbuild.builder.subprocess.run", return_value=SimpleNamespace(
                stdout=temp + "\n")):
                with self.assertRaisesRegex(RuntimeError, "found no vcvarsall"):
                    patch_arm_sdk()

    def test_file_without_assignment_reports_match_problem(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.installation(root, b"@echo off\r\nset OTHER=ok\r\n")
            with patch("ffbuild.builder.subprocess.run", return_value=SimpleNamespace(
                stdout=str(root) + "\n")):
                with self.assertRaisesRegex(RuntimeError, "no __VCVARSALL_WINSDK"):
                    patch_arm_sdk()

    def test_only_arm_triplet_requires_patch(self):
        for triplet in ("arm64-windows", "x64-windows", "x86-windows"):
            with self.subTest(triplet=triplet), patch("ffbuild.ci.patch_arm_sdk") as helper:
                ci_main(["prepare-host", f"--triplet={triplet}"])
                helper.assert_not_called()
        with patch("ffbuild.ci.patch_arm_sdk") as helper:
            ci_main(["prepare-host", "--triplet=arm-windows"])
            helper.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
