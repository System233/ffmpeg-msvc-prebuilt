# Cross-Compile / NASM / Architecture Fixes

These patches handle x86 32-/64-bit assembly compatibility and ARM cross-compilation issues.

## Patches

| Patch | Versions | What it fixes |
|-------|----------|--------------|
| `0005-fix-nasm-5.1` | 5.x | Guards x86 asm objects behind `ifdef ARCH_X86_64` in Makefiles — prevents NASM from trying to assemble 64-bit-only instructions on 32-bit builds |
| `0005-fix-nasm-6.0` | 6.x | Same Makefile-level guard approach for 6.x |
| `0005-fix-nasm-7.0` | 7.x | Same + adds VVC decoder asm files |
| `0005-fix-nasm-7.1` | 7.x | **New approach**: inverts `%if ARCH_X86_64` inside .asm files with placeholder data, instead of Makefile guards |
| `0005-fix-nasm-8.0` | 8.x | Same .asm-level placeholder approach for 8.x — handles apv_dsp, mlpdsp, proresdsp, vp9itxfm, vvc/mc, atadenoise, nlmeans |
| `0005-fix-nasm-8.1` | 8.x | Same + vp9itxfm_avx2 |
| `0024-fix-gcc13-binutils` | 5.x | Fixes inline asm constraint `"ci"` for GCC 13/binutils compatibility |
| `0042-fix-arm64-linux` | 6.x | Adds shebang to `ffbuild/libversion.sh` so it runs on Linux |

## Two approaches for NASM (version-dependent)

**Makefile approach** (5.x, 6.x): Guards .o files behind `ifdef ARCH_X86_64` in `libavcodec/x86/Makefile` and `libavfilter/x86/Makefile`.

**.asm placeholder approach** (7.1, 8.x): Inverts the `%if ARCH_X86_64` condition inside each .asm file, providing placeholder data for 32-bit.

When adding a new version, check which approach is used and follow the same pattern.

## When to check this category

- `nasm not found` even though NASM is installed
- Assembly errors about 64-bit instructions on 32-bit builds
- ARM cross-compilation failures related to script execution
