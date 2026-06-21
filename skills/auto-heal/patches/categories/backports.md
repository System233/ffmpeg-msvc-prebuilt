# Upstream Backports

These patches fix bugs that were later fixed upstream but were backported to older versions in this repo.

## Patches

| Patch | Versions | Files | What it fixes |
|-------|----------|-------|--------------|
| `0048-backport-23039` | 8.x | `configure`, `libavformat/`, `libavcodec/` (8 files) | Refactors CBS (Coded Bitstream) support. Creates `CBS_APV_LAVF`/`CBS_AV1_LAVF` config options, moves `all_codec_ids[]` from `libavcodec/cbs.c` to `libavcodec/cbs_bsf.c`. Fixes compilation with certain config combinations. |
| `0043-fix-miss-head-7.0` | 7.x | `libavfilter/textutils.c` | Adds missing `#include "libavutil/time_internal.h"` for FFmpeg 7.0. Fixes implicit function declaration error. |
| `0043-fix-miss-head-7.1` | 7.x | `libavfilter/textutils.c` | Same missing include fix for 7.1. |
| `0022-fix-m1-hardware-decode-nal-bits` | 4.x | `libavcodec/h264_ps.c` | Re-adds stop bits (0x80) to SPS/PPS NAL data for Apple VideoToolbox hardware decoder compatibility. |

## When to check this category

- Compiler errors about implicit function declarations
- CBS-related build failures
- Apple hardware decoder issues
- Errors in files that normally shouldn't be touched (textutils, cbs)
