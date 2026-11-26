# ARM-Specific Workarounds

## Patches

| Patch | Versions | File | What it fixes |
|-------|----------|------|--------------|
| `0020-fix-aarch64-libswscale` | 4.x, 5.x, 6.x, 7.x, 8.x | `libswscale/aarch64/yuv2rgb_neon.S` | Removes trailing comments (`// 1 2 3 0`) from `.ifc` directives in NEON assembly. Some assemblers (gas, clang) fail on these comments. |

This is the same fix applied across 5 major versions. The file path is identical across all versions.

## When to check this category

- ARM64 NEON assembly build errors
- `.ifc` directive assembler errors
- Build only fails on `arm64` or `arm` but not `x64`/`x86`
