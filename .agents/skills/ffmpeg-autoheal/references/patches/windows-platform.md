# Windows Platform Fixes

Small but critical category. These patches add Windows-specific preprocessor defines needed for MSVC compilation.

## Patches

| Patch | Versions | File | What it fixes |
|-------|----------|------|--------------|
| `0003-fix-windowsinclude` | 4.x, 5.x, 6.x, 7.x, 8.x | `fftools/cmdutils.c` | Defines `_WIN32_WINNT=0x0502` + `WIN32_LEAN_AND_MEAN` before `<windows.h>` include. Without this, Windows headers pull in too much or use unavailable APIs. |
| `0013-define-WINVER` | 4.x, 5.x, 6.x, 7.x, 8.x | `libavcodec/mf_utils.c` | Defines `WINVER=0x0602` so MediaFoundation APIs are available on older Windows SDKs. |
| `0012-fix-opengl-unistd` | 3.x | `libavdevice/opengl_enc.c` | Guards `#include <unistd.h>` with `#if HAVE_UNISTD_H` — MSVC doesn't provide this header. |

## When to check this category

- Compiler error about missing `unistd.h`
- Compiler error about `CreateFile`/`CreateEvent`/Windows API conflicts
- MediaFoundation compilation errors about missing types
