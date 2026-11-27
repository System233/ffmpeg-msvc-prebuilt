from pathlib import Path
import json
import unittest
import tempfile
from unittest.mock import patch

from ffbuild.compliance import resolve_port_license, supplemental_license
from ffbuild.license_policy import evaluate, Status


def document(value=None, declared="NOASSERTION"):
    return {"spdxVersion": "SPDX-2.2", "packages": [
        {"name": "sample", "SPDXID": "SPDXRef-port", "licenseConcluded": value,
         "licenseDeclared": declared},
        {"name": "sample:x64-windows", "SPDXID": "SPDXRef-binary",
         "licenseConcluded": value, "licenseDeclared": declared}]}


class SupplementalDeclarationTests(unittest.TestCase):
    def test_directory_fallback_only_for_missing_assertions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
                   "name": "sample supplemental license",
                   "documentNamespace": "https://example.org/spdx/sample/1",
                   "creationInfo": {"creators": ["Tool: test"], "created": "2026-11-25T00:00:00Z"},
                   "packages": [{"name": "sample", "SPDXID": "SPDXRef-port", "versionInfo": "1.0#2",
                                 "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                                 "licenseConcluded": "BSD-3-Clause", "licenseDeclared": "NOASSERTION",
                                 "copyrightText": "NOASSERTION", "sourceInfo": "https://example.org/1.0/LICENSE"}]}
            (root / "sample.spdx.json").write_text(json.dumps(row))
            with patch("ffbuild.compliance.LICENSE_DECLARATIONS", root):
                def resolve(doc, version="1.0", revision=2):
                    return resolve_port_license(doc, "sample:x64-windows", version, revision, b"notice")
                for unknown in (None, "NOASSERTION", "LicenseRef-vcpkg-null"):
                    self.assertEqual(("BSD-3-Clause", "local-declaration", row),
                                     resolve(document(unknown)))
                self.assertEqual(("GPL-3.0-only", "licenseConcluded", None),
                                 resolve(document("GPL-3.0-only")))
                self.assertEqual(("MIT", "licenseDeclared", None),
                                 resolve(document(None, "MIT")))
                for doc, version, revision in ((document(), "1.1", 2), (document(), "1.0", 3),
                    (document("MIT AND LicenseRef-vcpkg-null"), "1.0", 2),
                    (document("NONE"), "1.0", 2),
                    (document("MIT", "GPL-3.0-only"), "1.0", 2)):
                    with self.assertRaises(ValueError):
                        resolve(doc, version, revision)
                inconsistent = document()
                inconsistent["packages"][1]["licenseConcluded"] = "GPL-3.0-only"
                with self.assertRaises(ValueError):
                    resolve(inconsistent)
                mismatched = document()
                mismatched["packages"][1]["name"] = "other:x64-windows"
                with self.assertRaisesRegex(ValueError, "identity differs"):
                    resolve(mismatched)

    def test_known_declarations_and_unresolved_custom_terms(self):
        from ffbuild.compliance import LICENSE_DECLARATIONS
        files = list(LICENSE_DECLARATIONS.glob("*.spdx.json"))
        self.assertTrue({"fastfeat", "ffnvcodec", "lensfun", "leptonica", "libarchive",
                         "libiconv", "liblzma", "libmodplug", "libtheora", "opengl",
                         "opengl-registry", "pkgconf", "snappy", "soxr", "spirv-headers",
                         "vcpkg-make", "vulkan", "vulkan-loader"} <= {p.name.removesuffix(".spdx.json") for p in files})
        for file in files:
            row = json.loads(file.read_text(encoding="utf-8"))
            pkg = row["packages"][0]
            name = file.name.removesuffix(".spdx.json")
            version, _, revision = pkg["versionInfo"].partition("#")
            with self.subTest(name=name):
                self.assertEqual("SPDX-2.3", row["spdxVersion"])
                self.assertTrue(pkg["licenseDeclared"])
                self.assertEqual(name, pkg["name"])
                self.assertIsNotNone(evaluate(pkg["licenseConcluded"], "LGPL-3.0-or-later"))
                if not row.get("files") and pkg["licenseConcluded"] != "NOASSERTION":
                    self.assertEqual(row, supplemental_license(name, version, int(revision or 0), b"copyright"))
        row = json.loads((LICENSE_DECLARATIONS / "opengl.spdx.json").read_text())
        self.assertEqual("NOASSERTION", row["packages"][0]["licenseConcluded"])
        self.assertIsNone(supplemental_license("opengl", "2022-12-04", 3, b"SDK reference"))
        self.assertEqual(Status.REVIEW, evaluate("NOASSERTION", "LGPL-3.0-or-later").status)

    def test_correction_requires_matching_native_expression_version_and_notice(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = b"verified upstream copyright"
            native = "GPL-3.0-only"
            corrected = "GPL-3.0-only WITH Bison-exception-2.2"
            row = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
                   "packages": [{"name": "sample", "SPDXID": "SPDXRef-port", "versionInfo": "1.0#2",
                                 "sourceInfo": "https://example.org/LICENSE", "licenseDeclared": native,
                                 "licenseConcluded": corrected}],
                   "files": [{"fileName": "./copyright", "checksums": [{"algorithm": "SHA256",
                              "checksumValue": hashlib.sha256(raw).hexdigest()}]}]}
            path = root / "sample.spdx.json"
            path.write_text(json.dumps(row))
            with patch("ffbuild.compliance.LICENSE_DECLARATIONS", root):
                self.assertEqual((corrected, "local-correction", row),
                    resolve_port_license(document(native), "sample:x64-windows", "1.0", 2, raw))
                for expr, version, notice in ((native, "1.1", raw), (native, "1.0", raw+b"changed"),
                                              ("MIT", "1.0", raw)):
                    self.assertEqual((expr, "licenseConcluded", None),
                        resolve_port_license(document(expr), "sample:x64-windows", version, 2, notice))
                with self.assertRaises(ValueError):
                    resolve_port_license(document(None), "sample:x64-windows", "1.0", 2, raw)
                row.pop("files")
                path.write_text(json.dumps(row))
                with self.assertRaisesRegex(ValueError, "Correction requires"):
                    resolve_port_license(document(native), "sample:x64-windows", "1.0", 2, raw)

    def test_external_sdk_requires_exact_recipe_and_import_only_payload(self):
        from ffbuild.compliance import external_system_declaration, verify_system_archive_members, _OPENGL_PORT_SHA256
        raw = b"See https://developer.microsoft.com/windows/downloads/windows-10-sdk for the Windows 10 SDK license."
        doc = document("LicenseRef-vcpkg-null")
        doc["packages"][0]["name"] = "opengl"
        doc["packages"][1]["name"] = "opengl:x64-windows"
        doc["files"] = [{"SPDXID": "SPDXRef-port-file-0", "fileName": "./portfile.cmake",
                         "checksums": [{"algorithm": "SHA256", "checksumValue": sorted(_OPENGL_PORT_SHA256)[0]}]}]
        doc["relationships"] = [{"spdxElementId": "SPDXRef-port", "relationshipType": "CONTAINS",
                                 "relatedSpdxElement": "SPDXRef-port-file-0"}]
        for i, filename in enumerate(("include/GL/gl.h", "include/GL/glu.h", "lib/OpenGL32.Lib", "lib/GlU32.Lib")):
            ref = f"SPDXRef-binary-file-{i}"
            doc["files"].append({"SPDXID": ref, "fileName": "./"+filename})
            doc["relationships"].append({"spdxElementId":"SPDXRef-binary","relationshipType":"CONTAINS","relatedSpdxElement":ref})
        def check():
            return external_system_declaration(doc, "opengl:x64-windows", "2022-12-04", 3, raw)
        self.assertIsNotNone(check())
        self.assertEqual(("NOASSERTION", "external-system"), resolve_port_license(
            doc, "opengl:x64-windows", "2022-12-04", 3, raw)[:2])
        doc["files"][0]["checksums"][0]["checksumValue"] = "a"*64
        self.assertIsNone(check())
        doc["files"][0]["checksums"][0]["checksumValue"] = sorted(_OPENGL_PORT_SHA256)[0]
        doc["files"][-1]["fileName"] = "./bin/implementation.dll"
        self.assertIsNone(check())
        verify_system_archive_members(["bin/ffmpeg.exe", "lib/avcodec.lib"], system_dependency=True)
        for name in ("lib/OpenGL32.Lib", "bin/opengl32.dll", "include/GL/gl.h"):
            with self.assertRaisesRegex(ValueError, "System SDK file"):
                verify_system_archive_members([name], system_dependency=True)

    def test_custom_license_requires_actual_extracted_text(self):
        from ffbuild.compliance import LICENSE_DECLARATIONS
        row = json.loads((LICENSE_DECLARATIONS / "libmodplug.spdx.json").read_text())
        row.pop("hasExtractedLicensingInfos")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "libmodplug.spdx.json").write_text(json.dumps(row))
            with patch("ffbuild.compliance.LICENSE_DECLARATIONS", root):
                with self.assertRaisesRegex(ValueError, "extracted licensing text"):
                    supplemental_license("libmodplug", "0.8.9.0", 15, b"notice")


if __name__ == "__main__":
    unittest.main()
