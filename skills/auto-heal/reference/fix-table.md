# Error → Fix Quick Reference

## Patch failures

| Error symptom | Root cause | Fix direction |
|-------------|-----------|--------------|
| `patch failed: configure: Hunk #N` | Dependency detection patch drifted across FFmpeg versions | Update `0004-dependencies-{ver}.patch` in the matching category |
| `patch failed: libavfilter/vf_lensfun.c` | lensfun API changed | Update `0050-lensfun-*` patch |
| `patch failed: libavcodec/libsvtav1.c` | SVT-AV1 API changed | Update `0052-svtav1-*` patch |
| `patch failed: ffbuild/libversion.sh` | Shell script changed between versions | Update or remove `0042-fix-arm64-linux` patch |
| `patch failed: ffbuild/common.mak` | Build system changed | Update `0045-use-prebuilt-bin2c-*` patch |
| `patch failed: libavcodec/libx264.c` | x264 API/imports changed | Update `0019-libx264-*` patch |
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

## YAML/Generation failures

| Error symptom | Root cause | Fix direction |
|-------------|-----------|--------------|
| `YAML file not found: ffmpeg/X.Y.Z.yaml` | Version YAML missing | Create the YAML or fix `extends` reference |
| `SHA512 mismatch` | Source tarball hash wrong | Update `source.sha512` in version YAML |
| `RecursionError` | Circular `@alias` references | Check `define` block for alias loops |
| Feature unexpectedly missing | Version gate too restrictive | Check `version:` field on the feature |
| Feature unexpectedly present | Version gate too loose | Add/restrict `version:` field on the feature |
| port not appearing in `ffport list` | YAML filename non-standard | Ensure filename matches X.Y or X.Y.Z pattern |
