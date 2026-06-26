"""Tests for scripts/ffport/yaml_utils.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ffport import yaml_utils, YAML_DIR


class TestYamlUtilsModule(unittest.TestCase):
    """Verify the yaml_utils module is correctly imported and exported."""

    def test_module_accessible_via_ffport(self):
        """ffport.yaml_utils is importable (catches rename breakage)."""
        import ffport
        self.assertTrue(hasattr(ffport, "yaml_utils"))

    def test_load_yaml_function_exists(self):
        """load_yaml is exposed on the module."""
        self.assertTrue(callable(yaml_utils.load_yaml))

    def test_resolve_chain_function_exists(self):
        """resolve_chain is exposed on the module."""
        self.assertTrue(callable(yaml_utils.resolve_chain))


class TestLoadYaml(unittest.TestCase):
    """Tests for yaml_utils.load_yaml()."""

    def test_loads_base_yaml(self):
        """Loading 'base' returns a dict with expected keys."""
        data = yaml_utils.load_yaml("base")
        self.assertIsInstance(data, dict)
        self.assertIn("features", data)
        self.assertIn("define", data)

    def test_loads_version_family_yaml(self):
        """Loading a version family (e.g. '8.1') returns valid data."""
        data = yaml_utils.load_yaml("8.1")
        self.assertIsInstance(data, dict)
        self.assertIn("extends", data)
        self.assertIn("source", data)

    def test_loads_patch_yaml(self):
        """Loading a specific patch version (e.g. '8.1.1') works."""
        data = yaml_utils.load_yaml("8.1.1")
        self.assertIsInstance(data, dict)

    def test_loads_master_yaml(self):
        """Loading 'master' returns valid data."""
        data = yaml_utils.load_yaml("master")
        self.assertIsInstance(data, dict)

    def test_file_not_found_exits(self):
        """Loading a non-existent YAML file exits with error."""
        with self.assertRaises(SystemExit):
            yaml_utils.load_yaml("nonexistent_version_xyz")

    def test_yaml_dir_exists(self):
        """YAML_DIR points to an existing directory with .yaml files."""
        self.assertTrue(YAML_DIR.is_dir())
        yamls = list(YAML_DIR.glob("*.yaml"))
        self.assertGreater(len(yamls), 0)


class TestResolveChain(unittest.TestCase):
    """Tests for yaml_utils.resolve_chain()."""

    def test_base_chain(self):
        """Resolving 'base' returns a 2-element chain with label 'base'."""
        docs, label = yaml_utils.resolve_chain("base")
        self.assertEqual(label, "base")
        self.assertGreaterEqual(len(docs), 2)

    def test_master_chain(self):
        """Resolving 'master' returns a chain with label 'master'."""
        docs, label = yaml_utils.resolve_chain("master")
        self.assertEqual(label, "master")
        self.assertGreaterEqual(len(docs), 2)

    def test_version_family_chain(self):
        """Resolving a version family (e.g. '8.1') returns proper chain."""
        docs, label = yaml_utils.resolve_chain("8.1")
        self.assertEqual(label, "8.1")
        # Chain: base → parent family → 8.1
        self.assertGreaterEqual(len(docs), 2)

    def test_patch_version_chain(self):
        """Resolving '8.1.1' returns chain that includes base, family, patch."""
        docs, label = yaml_utils.resolve_chain("8.1.1")
        self.assertEqual(label, "8.1")
        # Chain includes base + intermediate family + 8.1 + 8.1.1
        self.assertGreaterEqual(len(docs), 3)

    def test_extended_parent_chain(self):
        """Resolving a version that extends from an older family works."""
        docs, label = yaml_utils.resolve_chain("7.1.5")
        self.assertEqual(label, "7.1")
        self.assertGreaterEqual(len(docs), 2)

    def test_custom_name_chain(self):
        """Resolving a non-version name (like 'master') uses custom chain."""
        docs, label = yaml_utils.resolve_chain("master")
        self.assertNotRegex(label, r"^\d+\.\d+$")

    def test_each_doc_is_dict(self):
        """Every document in the chain is a dict."""
        docs, _ = yaml_utils.resolve_chain("8.1.1")
        for doc in docs:
            self.assertIsInstance(doc, dict)

    def test_chain_extends_from_base(self):
        """The first document in every chain is always base.yaml."""
        docs, _ = yaml_utils.resolve_chain("8.1.1")
        first = docs[0]
        self.assertIn("features", first)
        # base.yaml is identified by its content, verify it has 'define'
        self.assertIn("define", first)

    def test_nonexistent_version_exits(self):
        """Resolving a completely invalid version exits with error."""
        with self.assertRaises(SystemExit):
            yaml_utils.resolve_chain("999.999.999")


if __name__ == "__main__":
    unittest.main()
