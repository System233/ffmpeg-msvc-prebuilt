# Build artifacts

## Binary and Debug

| Content | Shared Binary | Shared Debug | Static Binary |
|---|---|---|---|
| FFmpeg CLI tools | Yes | No | Yes |
| Headers, import libraries, DLLs | Yes | Debug libraries and DLLs only | No SDK |
| CMake and pkg-config integration | Yes | No | No |
| PDB symbols | — | Yes (as supplied) | — |

The Shared SDK supports dynamic linking. A complete static SDK would include many third-party static libraries and be too large to distribute, so Static builds ship standalone command-line tools only. For static linking in your application, [build from source](../self-build/). Static executables do not require separate FFmpeg DLLs.

### Debug (shared only, requires Binary)

Extract Debug over Shared Binary from the same build batch, architecture, license and linkage. Older Develop archives are standalone complete packages and do not require a separate Binary.

- `bin/`: Release DLLs; matching Release PDBs are supplied by Debug.
- `debug/lib/`: Debug import libraries.
- `debug/bin/`: Debug DLLs and matching PDBs.
- CLI EXE PDBs are supplied only when generated and matched.

See [debug builds and symbols](../integration/#debug-builds-and-symbols).

## Directory layout

| Path | Content |
|---|---|
| `bin/` | Shared executables and DLLs |
| `include/` | Shared SDK headers |
| `lib/` | Shared import libraries and pkg-config files |
| `share/ffmpeg/` | CMake module and compliance files |
| `debug/` | Optional Debug libraries |
| `LICENSE.txt` | Primary license |

Static archives typically contain CLI tools at the archive root. Historical archives may have different layouts.

## File naming

```text
ffmpeg-9.1_x64-windows-static-lgpl-261125.zip
ffmpeg-9.1_arm64-windows-shared-gpl-261125.zip
ffmpeg-9.1_arm64-windows-shared-gpl-debug-261125.zip
ffmpeg-master_x64-windows-static-gpl-261125.zip
```

These are filename format examples. Dates use UTC YYMMDD; same-day Release tags can have R2, R3 and later suffixes. Public filenames omit ABI and packaging format identifiers. Reused archives retain their original names and SHA-256; older archives may use revision-based names.

The standard matrix has 16 build variants (4 architectures × 2 licenses × 2 linkages), with 24 ZIPs for a complete publication (8 Static, 8 Shared, 8 Debug). Check the download page for actual availability.

## Related documentation

[Guide](../guide/) · [Integration](../integration/) · [Licenses and redistribution](../licenses/)
