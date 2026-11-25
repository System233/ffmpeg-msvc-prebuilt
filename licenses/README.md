# Supplemental Port licenses

One standard SPDX 2.3 JSON document (`<port>.spdx.json`) per dependency
whose native vcpkg SPDX has no license assertion. Use the vcpkg version
string in `packages[0].versionInfo` (append #port-version only when nonzero),
`licenseConcluded` for our evidence-based conclusion, and
`licenseDeclared: NOASSERTION` to preserve the distinction from native
metadata. Record the upstream URL in `sourceInfo`, scope in
`licenseComments`, and actual custom license text in
`hasExtractedLicensingInfos`. Unresolved terms remain NOASSERTION.

Native licenses take precedence. No blanket compatibility exemption is
created by a supplemental SPDX document. Exact notice checksums, when
provided in a standalone SPDX copyright file record, must match the
installed notice. Compatibility approvals remain in ffbuild/license_reviews.yaml.
Original vcpkg SPDX and copyright remain in the ZIP. Update the document
namespace and policy version when the declaration changes.

A correction to a known native expression is allowed only when the local SPDX package's licenseDeclared matches the same SPDX syntax tree (ignoring AND/OR ordering), the Port version matches, and the installed copyright SHA256 matches the SPDX file checksum. The original SPDX is preserved; the normal compatibility gate still applies. glslang is the initial correction.
