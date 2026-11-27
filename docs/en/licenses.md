# Licenses and redistribution

## Choosing a license

Choose a license profile based on the actual enabled components and your use, linking and distribution model, not just the download label.

| Build | Meaning |
|---|---|
| GPL | May include GPL components such as x264 and x265; comply with applicable GPL terms. |
| LGPL | The updated build process restricts incompatible components; historical builds have disclosed risks. |
| Nonfree | Not a redistributable build profile. |

Run `ffmpeg -buildconf` to inspect configuration and `ffmpeg -encoders` to inspect available encoders. Neither output alone proves license compliance.

## Historical LGPL builds

Some historical LGPL builds have GPL component or other license compatibility issues. Do not treat an archive carrying a risk notice as a verified LGPL build. See the [licensing notice in the update history](../history/#legacy-lgpl-builds) for confirmed evidence, fixes and outstanding matters. Fixes apply to new builds; historical archives still require individual verification.

## Redistribution checklist

When embedding FFmpeg or distributing its binaries with your application:

1. Identify the actual build, components and applicable licenses.
2. Preserve required license texts, copyright notices and other attribution.
3. Meet applicable corresponding-source obligations, including relevant modifications and build materials.
4. Evaluate the linking and distribution model; where applicable, meet LGPL requirements for library replacement or relinking.
5. Review independent third-party license requirements.

Using Shared DLLs or including an SPDX file alone does not satisfy these obligations automatically. Evaluate the actual distribution model against the applicable license texts.

## License files in archives

Updated build artifacts include:

| File | Purpose |
|---|---|
| `LICENSE.txt` | Primary license |
| `share/ffmpeg/copyright` | Combined copyright notices |
| `share/ffmpeg/sbom.spdx.json` | SPDX 2.3 dependency information |

The updated publication process adds explicit license compatibility and archive evidence checks. The SBOM records installed dependencies; it does not independently establish the final linked objects or replace corresponding-source and other license obligations. Original dependency evidence and build provenance are retained outside the archive.

For custom components, see the [feature reference](../reference/) and [self-build guide](../self-build/).
