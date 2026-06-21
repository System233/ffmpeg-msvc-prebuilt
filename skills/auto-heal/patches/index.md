# Patch Overview

## Patch count by version

| Major | Patch count |
|-------|------------|
| 3.x | 14 |
| 4.x | 23 |
| 5.x | 22 |
| 6.x | 16 |
| 7.x | 20 |
| 8.x | 28 |

## Most frequently patched files

| File | Patched in versions |
|------|-------------------|
| `configure` | ALL versions — 70+ patch entries total |
| `libavfilter/vf_lensfun.c` | 4.x, 5.x, 6.x, 7.x, 8.x |
| `libswscale/aarch64/yuv2rgb_neon.S` | 4.x, 5.x, 6.x, 7.x, 8.x |
| `libavcodec/mf_utils.c` | 4.x, 5.x, 6.x, 7.x, 8.x |
| `fftools/cmdutils.c` | 4.x, 5.x, 6.x, 7.x, 8.x |
| `libavcodec/libsvtav1.c` | 4.x, 5.x, 6.x, 7.x |
| `libavcodec/libx264.c` | 3.x, 4.x, 5.x |
| `libavformat/avformat.h` | 6.x, 7.x, 8.x |
| `ffbuild/common.mak` | 8.x |

## Category breakdown

| Category | Count | Typical failure |
|----------|-------|-----------------|
| `msvc-toolchain.md` | 20+ | MSVC not detected, wrong flags, link errors |
| `dependencies.md` | 15+ | "ERROR: libxxx not found" |
| `windows-platform.md` | 3 | Missing WINVER/WIN32_LEAN_AND_MEAN defines |
| `cross-compile.md` | 8 | NASM errors on 32-bit, ARM arch issues |
| `arm.md` | 1x5 versions | AArch64 NEON asm build error |
| `library-naming.md` | 1x6 versions | Wrong .lib/.a extension |
| `backports.md` | 3 | Missing upstream fixes |
| `features.md` | 3 | Feature not enabled/disabled correctly |

## Directory structure

```
patches/
├── 3.x/  (14 patches)
├── 4.x/  (23 patches)
├── 5.x/  (22 patches)
├── 6.x/  (16 patches)
├── 7.x/  (20 patches)
└── 8.x/  (28 patches)
```

Patch naming pattern: `{NNNN}-{description}-{version-suffix}.patch`
- `0002-fix-msvc-link-8.1.patch` — number groups by topic, version suffix shows target
- `0003-fix-windowsinclude.patch` — no suffix = version-agnostic
- `0050-lensfun-0.3.4-compat-8.x.patch` — "8.x" means any 8.x version
