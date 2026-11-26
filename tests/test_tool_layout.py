"""Repository-owned portable skills and installed module entry points."""
import importlib.util
from pathlib import Path
import unittest
import yaml
from ffbuild.versions import ROOT

class ToolLayoutTests(unittest.TestCase):
    def test_packages_are_installed_from_scripts(self):
        for name in ("ffbuild", "ffvcpkg"):
            spec = importlib.util.find_spec(name)
            self.assertEqual(ROOT / "scripts" / name / "__init__.py", Path(spec.origin).resolve())
        for removed in ("scripts/ci", "scripts/ops", "scripts/ffport", "scripts/ffport.py"):
            self.assertFalse(any(p.is_file() and p.suffix in (".py", ".ps1", ".sh")
                                 for p in (ROOT / removed).rglob("*")), removed)

    def test_workflows_use_repository_owned_skills(self):
        skill = ROOT / ".agents/skills/ffmpeg-autoheal/SKILL.md"
        self.assertTrue(skill.is_file())
        prompt = (ROOT / "scripts/ffbuild/autoheal/prompts/repair.md").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/ffmpeg-autoheal/SKILL.md", prompt)
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            source = path.read_text(encoding="utf-8")
            self.assertIsInstance(yaml.safe_load(source), dict)
            for old in ("python scripts/ci/", "python scripts/ops/", "python scripts/ffport.py",
                        "git fetch origin opencode", "opencode/skills/"):
                self.assertNotIn(old, source, path.name)

    def test_legacy_packaging_rejected_before_writing(self):
        from tempfile import TemporaryDirectory
        from ffbuild.package import package_job
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaisesRegex(ValueError, "Native dated Build Plan"):
                package_job(directory, {"port": "ffmpeg"}, directory / "out")
            self.assertFalse((directory / "out").exists())


    def test_legacy_catalog_staging_is_rejected(self):
        from tempfile import TemporaryDirectory
        from ffbuild.catalog import stage_index
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "legacy YAML is read-only"):
                stage_index(Path(tmp))
