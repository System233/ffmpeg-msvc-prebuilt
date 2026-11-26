# MSVC Toolchain Fixes

Largest category (20+ patches). Fix MSVC compiler detection, flag translation, linking, and build tool integration.

## Key patches

| Patch | Versions | Modifies | What it fixes |
|-------|----------|----------|--------------|
| `0002-fix-msvc-link` | 5.x, 6.x, 7.x, 8.x | `configure` | NASM debug symbol format for Windows COFF |
| `0007-fix-lib-naming` | 3.x, 4.x, 5.x, 6.x, 7.x, 8.x | `configure` | Translates `-lx265` → `libx265.lib`, `-lmp3lame` → `libmp3lame.lib`, strips `-lm` |
| `0010-fix-opencl` | 3.x | `configure` | Adds Advapi32/Ole32/Cfgmgr32 for OpenCL static linking |
| `0011-fix-opengl-quoting` | 3.x | `configure` | Removes double quotes in OpenGL check for MSVC flag splitting |
| `0013-fix-x264-imports` | 3.x | `libavcodec/libx264.c` | Removes `X264_API_IMPORTS` for static x264 |
| `0017-Patch-for-ticket-9019-CUDA-MSVC` | 4.x | `configure`, `ptx2c.sh` | Rewrites ptx2c.sh for MSVC CUDA compilation |
| `0019-libx264-Do-not-explicitly-set-X264_API_IMPORTS` | 4.x, 5.x | `configure`, `libx264.c` | Forces pkg-config x264 detection |
| `0041-add-const-for-opengl-definition` | 6.x, 7.x | `libavdevice/opengl_enc.c` | Fixes OpenGL function pointer const qualifier |
| `0044-fix-vulkan-debug-callback-abi` | 7.x | `libavutil/hwcontext_vulkan.c` | Adds `VKAPI_ATTR` for Vulkan callback ABI |
| `0045-use-prebuilt-bin2c` | 8.x | `ffbuild/common.mak` | Uses prebuilt bin2c instead of building from source |
| `0046-fix-msvc-detection` | 8.x | `configure` | Case-insensitive MSVC detection (`grep -qi Microsoft`) |
| `0047-fix-msvc-utf8` | 8.x | `configure` | Applies `-utf-8` flag to host compiler too |
| `0052-fix-msvc-flags-filter` | 8.x | `configure` | Silently drops `-Werror=*` for MSVC, passes `-U*` |
| `0053-fix-host-cc-msvc` | 8.x | `configure` | Defaults host CC to MSVC when toolchain=msvc |
| `0054-fix-opstool-aarch64` | 8.x | `libswscale/aarch64/Makefile` | Uses prebuilt ops_asmgen instead of building from source |
| `0001-fix-iconv-link` | 4.x | `configure` | Adds `-liconv` fallback detection for MSVC |
| `0004-fix-debug-build` | 4.x, 5.x | `configure` | Debug build uses `-lbz2d` debug variants |
| `windres-configure-fix` | 3.x | `configure` | Adds windres to CMDLINE_SET |

## When to check this category

- CI shows `LNK2001`/`LNK2019` unresolved externals
- `--toolchain=msvc` not being set in configure
- Compiler detection failures
- Build tool (bin2c/ops_asmgen) issues
- OpenGL/Vulkan/OpenCL linking errors
