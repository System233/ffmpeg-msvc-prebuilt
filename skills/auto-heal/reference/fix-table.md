# Error → Fix Quick Reference

## Patch failures

| Error symptom | Root cause | Fix direction |
|-------------|-----------|--------------|
 | `patch failed: configure: Hunk #N` | Dependency detection patch drifted across FFmpeg versions | Remove from YAML `patches:` or add a version-specific replacement |
| `patch failed: libavfilter/vf_lensfun.c` | lensfun API changed | Add a new version-specific `0050-lensfun-*` patch (never modify existing) |
| `patch failed: libavcodec/libsvtav1.c` | SVT-AV1 API changed | Add a new version-specific `0052-svtav1-*` patch (never modify existing) |
| `patch failed: ffbuild/libversion.sh` | Shell script changed between versions | Remove from YAML `patches:` (upstream already has it) |
| `patch failed: ffbuild/common.mak` | Build system changed | Add a new version-specific `0045-use-prebuilt-bin2c-*` patch (never modify existing) |
| `patch failed: libavcodec/libx264.c` | x264 API/imports changed | Add a new version-specific `0019-libx264-*` patch (never modify existing) |
| Multiple hunks with large offset | Patch applied but context shifted significantly | Check if this is the right patch variant for the version |

## Configure/build failures

| Error symptom | Root cause | Fix direction |
|-------------|-----------|--------------|
| `ERROR: libmp3lame not found` | Static linking detection failed | Check `0004-dependencies` patch for mp3lame section |
| `ERROR: libx265 not found` | x265 detection failed | Check `0011-Fix-x265-detection` patch or update x265 version in port |
| `ERROR: libxml2 not found` | Incorrect header path | Check `0015-Fix-xml2-detection` patch |
| `ERROR: libfdk-aac not found` | FDK-AAC detection missing libs | Check `0009-Fix-fdk-detection` patch |
| `ERROR: openssl not found` | OpenSSL 1.1 detection missing `-ldl` | Check `0012-Fix-ssl-110-detection` patch |
| `ERROR: libjxl not found` | libjxl detection in 5.x | Check `0051-libjxl-0.11-compat` patch |
| `nasm not found` / `no working assembler` | NASM missing or wrong arch | Check `0005-fix-nasm-*` patch for the version |
| `fatal error C1083: Cannot open include file` | Missing header (often from patch) | Check the patch that touches that file |
| `LNK2001 unresolved external symbol` | Missing export or wrong lib | Check library-naming patch or dependency patch |
| `LNK2019 unresolved external symbol` | Same as above | Check `0007-fix-lib-naming` patch |
| `--toolchain=msvc` not set | MSVC not detected | Check `0046-fix-msvc-detection` + `0053-fix-host-cc-msvc` patches |
| `Error: ffmpeg will not build with spaces in the path` | Source path has spaces | CI runner issue (not patch/YAML) |

> **Note on existing patches**: If the failing patch is listed in agent_context.json's `new_patches`, you may modify it directly. Otherwise, remove it from the YAML `patches:` list to disable it for the failing version, or add a new replacement patch.

## YAML/Generation failures

| Error symptom | Root cause | Fix direction |
|-------------|-----------|--------------|
| `YAML file not found: ffmpeg/X.Y.Z.yaml` | Version YAML missing | Create the YAML or fix `extends` reference |
| `SHA512 mismatch` | Source tarball hash wrong | Update `source.sha512` in version YAML |
| `RecursionError` | Circular `@alias` references | Check `define` block for alias loops |
| Feature unexpectedly missing | Version gate too restrictive | Check `version:` field on the feature |
| Feature unexpectedly present | Version gate too loose | Add/restrict `version:` field on the feature |
| port not appearing in `ffport list` | YAML filename non-standard | Ensure filename matches X.Y or X.Y.Z pattern |
