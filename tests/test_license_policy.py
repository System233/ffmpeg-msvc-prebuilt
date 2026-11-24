"""SPDX policy, scope classification, and archive integrity regressions."""
from __future__ import annotations

import unittest
import tempfile
import json
import hashlib
import base64
from unittest.mock import patch
from pathlib import Path

from ffbuild.license_policy import evaluate, Status, require_compatible, scoped_compatibility, same_expression
from ffbuild.compliance import dependency_scopes, reachable_ports, _dependency_keys, verified_manifest_hosts, manifest_host_edges


class LicensePolicyTests(unittest.TestCase):
    def test_expression_and_gnu_matrix(self):
        cases = [
            ("MIT", "LGPL-3.0-or-later", Status.ALLOW),
            ("curl AND ISC AND BSD-3-Clause", "LGPL-3.0-or-later", Status.ALLOW),
            ("libtiff", "GPL-2.0-only", Status.ALLOW),
            ("Apache-2.0", "LGPL-3.0-or-later", Status.ALLOW),
            ("Apache-2.0", "GPL-3.0-or-later", Status.ALLOW),
            ("Apache-2.0", "GPL-2.0-only", Status.DENY),
            ("Apache-2.0", "LGPL-2.1-or-later", Status.DENY),
            ("GPL-2.0-only", "GPL-3.0-or-later", Status.DENY),
            ("GPL-2.0-or-later", "GPL-3.0-or-later", Status.ALLOW),
            ("GPL-2.0+", "GPL-3.0-or-later", Status.ALLOW),
            ("GPL-3.0-only", "GPL-2.0-only", Status.DENY),
            ("GPL-2.0-only", "GPL-2.0-only", Status.ALLOW),
            ("GPL-3.0-only", "LGPL-3.0-or-later", Status.DENY),
            ("GPL-3.0-only OR MIT", "LGPL-3.0-or-later", Status.ALLOW),
            ("GPL-3.0-only AND (MIT OR BSD-3-Clause)", "LGPL-3.0-or-later", Status.DENY),
            ("(GPL-3.0-only AND MIT) OR BSD-3-Clause", "LGPL-3.0-or-later", Status.ALLOW),
            ("(GPL-3.0-only OR MIT) AND (Zlib OR GPL-2.0-only)", "LGPL-3.0-or-later", Status.ALLOW),
            ("GPL-3.0-only OR LicenseRef-Unknown", "LGPL-3.0-or-later", Status.REVIEW),
            ("MIT AND LicenseRef-Unknown", "LGPL-3.0-or-later", Status.REVIEW),
            ("LicenseRef-MIT-Bootstrap", "LGPL-3.0-or-later", Status.REVIEW),
            ("GPL-2.0-only WITH Classpath-exception-2.0", "LGPL-3.0-or-later", Status.REVIEW),
            ("(GPL-2.0-only WITH Classpath-exception-2.0) OR MIT", "LGPL-3.0-or-later", Status.ALLOW),
            ("AGPL-3.0-or-later", "GPL-3.0-or-later", Status.DENY),
            ("LGPL-3.0-only", "GPL-2.0-only", Status.DENY),
            ("LGPL-2.0-only", "LGPL-3.0-or-later", Status.ALLOW),
            ("LGPL-2.1-or-later", "GPL-3.0-or-later", Status.ALLOW),
            ("MPL-2.0", "GPL-3.0-or-later", Status.ALLOW),
            ("MPL-2.0", "LGPL-3.0-or-later", Status.ALLOW),
            ("MPL-2.0-no-copyleft-exception", "LGPL-3.0-or-later", Status.REVIEW),
            ("MIT-Modern-Variant", "LGPL-3.0-or-later", Status.ALLOW),
            ("BSD-3-Clause-Clear", "LGPL-3.0-or-later", Status.ALLOW),
            ("OpenSSL", "GPL-3.0-or-later", Status.REVIEW),
            ("BSD-4-Clause", "GPL-3.0-or-later", Status.DENY),
        ]
        for expression, main, status in cases:
            with self.subTest(expression=expression, main=main):
                self.assertEqual(status, evaluate(expression, main).status)

    def test_native_expression_order_is_ignored_without_dropping_terms(self):
        self.assertTrue(same_expression("MIT AND (BSD-3-Clause AND GPL-3.0-only)",
                                        "GPL-3.0-only AND MIT AND BSD-3-Clause"))
        self.assertFalse(same_expression("MIT AND GPL-3.0-only", "MIT OR GPL-3.0-only"))
        self.assertFalse(same_expression("MIT AND (MIT OR GPL-3.0-only)", "MIT"))
        self.assertFalse(same_expression("GPL-3.0-only WITH Bison-exception-2.2", "GPL-3.0-only"))

    def test_or_returns_complete_witness_not_just_a_boolean(self):
        result = evaluate("(GPL-3.0-only OR MIT) AND (GPL-2.0-only OR Zlib)",
                          "LGPL-3.0-or-later")
        self.assertEqual(Status.ALLOW, result.status)
        self.assertEqual(("MIT", "Zlib"), result.selected)

    def test_invalid_and_unknown_expression_fails_closed(self):
        for expression in ("", "MIT AND", "(MIT OR BSD-3-Clause", "MIT BSD-3-Clause", "MIT WITH"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                require_compatible(expression, "LGPL-3.0-or-later", "dependency")
        for expression in ("LicenseRef-Foo", "Unknown-1.0", "NOASSERTION"):
            with self.subTest(expression=expression), self.assertRaisesRegex(ValueError, "License review"):
                require_compatible(expression, "LGPL-3.0-or-later", "dependency")

    def test_reviewed_custom_terms_are_contextual(self):
        expression = "LicenseRef-Pkgconf-2.5.1"
        self.assertEqual(Status.REVIEW, evaluate(expression, "LGPL-3.0-or-later").status)
        self.assertEqual(Status.ALLOW, evaluate(expression, "LGPL-3.0-or-later",
                                               reviewed=frozenset({expression})).status)

    def test_build_tool_is_not_target_copyleft(self):
        self.assertEqual(Status.DENY, evaluate("GPL-3.0-only", "LGPL-3.0-or-later").status)
        result = evaluate("GPL-3.0-only", "LGPL-3.0-or-later", build_only=True)
        self.assertEqual(Status.ALLOW, result.status)
        self.assertEqual((), result.selected)

    def test_manual_review_matches_exact_identity_and_never_overrides_deny(self):
        expression = "GPL-2.0-only WITH Classpath-exception-2.0"
        main = "LGPL-3.0-or-later"
        identity = dict(name="example", version="1.0", port_revision=2,
                        copyright_sha256="a"*64, linkage="shared", build_only=False)
        row = dict(id="audit-1", package="example", version="1.0", port_revision=2,
                   copyright_sha256="a"*64, expression=expression, term=expression,
                   profile=main, linkage="shared", source="https://example.org/license", reason="Reviewed use")
        with patch("ffbuild.license_policy.load_reviews", return_value=(row,)):
            result = scoped_compatibility(expression, main, "example:x64-windows", **identity)
            self.assertEqual(["audit-1"], result["review_ids"])
            with self.assertRaisesRegex(ValueError, "License review"):
                scoped_compatibility(expression, main, "example:x64-windows", **dict(identity, linkage="static"))
            with self.assertRaisesRegex(ValueError, "License review"):
                scoped_compatibility(expression, main, "example:x64-windows", **dict(identity, copyright_sha256="b"*64))
        with patch("ffbuild.license_policy.load_reviews", return_value=(dict(row, expression="GPL-3.0-only", term="GPL-3.0-only"),)):
            with self.assertRaisesRegex(ValueError, "License deny"):
                scoped_compatibility("GPL-3.0-only", main, "example:x64-windows", **identity)


class DependencyScopeTests(unittest.TestCase):
    def test_same_name_different_triplets_remain_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "vcpkg/status"
            status.parent.mkdir()
            rows = [("ffmpeg", "arm-windows", "zlib, tool:x64-windows"),
                    ("zlib", "arm-windows", ""), ("tool", "x64-windows", "zlib"),
                    ("zlib", "x64-windows", "")]
            status.write_text("\n\n".join(
                f"Package: {name}\nVersion: 1\nArchitecture: {triplet}\nDepends: {deps}\nStatus: install ok installed"
                for name, triplet, deps in rows), encoding="utf-8")
            ports = reachable_ports(root, "arm-windows")
            self.assertEqual(4, len(ports))
            edges = {(p.name, p.triplet): p.dependency_keys for p in ports}
            scope = dependency_scopes(edges, ("ffmpeg", "arm-windows"), set())
            self.assertEqual("target-candidate", scope[("zlib", "arm-windows")])
            self.assertEqual("build-only", scope[("zlib", "x64-windows")])
            self.assertEqual("build-only", scope[("tool", "x64-windows")])
            self.assertEqual({("zlib", "arm-windows"), ("tool", "x64-windows")},
                             _dependency_keys("zlib, tool:x64-windows", "arm-windows"))

    def test_same_triplet_host_root_and_target_path_take_precedence(self):
        f, tool, common, lib, hostlib = ((name, "x64-windows") for name in
                                         ("ffmpeg", "tool", "common", "lib", "hostlib"))
        edges = {f: {tool, lib}, tool: {common, hostlib}, lib: {common},
                 common: set(), hostlib: set()}
        result = dependency_scopes(edges, f, {"tool"})
        self.assertEqual("build-only", result[tool])
        self.assertEqual("build-only", result[hostlib])
        self.assertEqual("target-candidate", result[common])
        self.assertEqual("target-candidate", result[lib])
        # Same architecture alone must not imply build-only.
        self.assertEqual("target-candidate", dependency_scopes(edges, f, set())[tool])

    def test_hash_verified_transitive_manifest_host_flags(self):
        f, lib, tool, common = ((name, "x64-windows") for name in ("ffmpeg", "lib", "tool", "common"))
        raw = json.dumps({"name": "lib", "dependencies": [
            {"name": "tool", "host": True}, {"name": "common", "host": True}],
            "features": {"extra": {"dependencies": ["common"]}}}).encode()
        spdx = {"files": [{"SPDXID": "SPDXRef-port-file-0", "fileName": "./vcpkg.json",
                           "checksums": [{"algorithm": "SHA256", "checksumValue": hashlib.sha256(raw).hexdigest()}]}],
                "relationships": [{"spdxElementId": "SPDXRef-port-file-0",
                                   "relationshipType": "DEPENDENCY_MANIFEST_OF", "relatedSpdxElement": "SPDXRef-port"}]}
        self.assertEqual({"tool"}, verified_manifest_hosts(raw, spdx, "lib", {"extra"}))
        with self.assertRaisesRegex(ValueError, "hash differs"):
            verified_manifest_hosts(raw + b" ", spdx, "lib", {"extra"})
        proofs = {"lib:x64-windows": base64.b64encode(raw).decode()}
        host_edges = manifest_host_edges(proofs, {lib: spdx}, {lib: {"extra"}})
        scopes = dependency_scopes({f: {lib}, lib: {tool, common}, tool: set(), common: set()},
                                   f, set(), host_edges)
        self.assertEqual("build-only", scopes[tool])
        self.assertEqual("target-candidate", scopes[common])

    def test_absent_exact_dependency_is_not_substituted_by_other_triplet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "vcpkg/status"
            status.parent.mkdir()
            status.write_text("Package: ffmpeg\nVersion: 1\nArchitecture: arm-windows\n"
                              "Depends: zlib\nStatus: install ok installed\n\n"
                              "Package: zlib\nVersion: 1\nArchitecture: x64-windows\n"
                              "Status: install ok installed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "zlib:arm-windows"):
                reachable_ports(root, "arm-windows")


if __name__ == "__main__":
    unittest.main()
