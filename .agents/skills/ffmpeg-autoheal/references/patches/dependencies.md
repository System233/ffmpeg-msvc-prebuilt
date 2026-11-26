# Dependency Compatibility

Second-largest category (15+ patches). This is the HIGHEST-FREQUENCY failure source — upstream libraries change API/detection between FFmpeg versions.

## Bulk dependency patches

These are the "catch-all" patches that fix multiple library detections at once:

| Patch | Versions | What it covers |
|-------|----------|---------------|
| `0004-dependencies-8.0` | 8.x | bzlib pkg-config, mp3lame static, snappy pkg-config, soxr -lm, OpenCL extra libs, iconv charset |
| `0004-dependencies-8.1` | 8.x | Same + converts zlib to `require_pkg_config` |
| `0004-dependencies-8.2` | 8.x | Same + zlib fix + iconv fix |
| `0004-dependencies-7.0` | 7.x | Same scope as 8.0 |
| `0004-dependencies-7.1` | 7.x | Same scope |
| `0004-dependencies-6.1` | 6.x | Same scope |
| `0006-fix-StaticFeatures` | 4.x, 5.x | mp3lame static, soxr -lm, OpenCL, OpenSSL, iconv charset |

## Individual library patches

| Library | Patch pattern | Versions |
|---------|--------------|----------|
| **lensfun** | `0050-lensfun-0.3.4-compat-*.patch` | 4.x, 5.x, 6.x, 7.x, 8.x |
| **lensfun configure** | `0051-lensfun-configure-fix-*.patch` | 7.x, 8.x |
| **SVT-AV1** | `0052-svtav1-3.x-compat-*.patch` | 4.x, 5.x, 6.x, 7.x |
| **libjxl** | `0051-libjxl-0.11-compat.patch` | 5.x |
| **x265** | `0011-Fix-x265-detection-*.patch` | 4.x, 5.x, 6.x |
| **x264** | `0010-Fix-x264-detection.patch` | 4.x |
| **FDK-AAC** | `0009-Fix-fdk-detection.patch` | 4.x, 5.x |
| **OpenSSL 1.1** | `0012-Fix-ssl-110-detection.patch` | 4.x, 5.x, 6.x, 7.x |
| **libxml2** | `0015-Fix-xml2-detection.patch` | 4.x, 5.x |
| **libmp3lame static** | `0006-fix-libmp3lame-static.patch` | 3.x |
| **openjpeg** | `0009-fix-openjpeg-lib-name.patch` | 3.x |
| **OpenCV** | `configure_opencv*.patch` | 3.x |
| **OpenSSL** | `detect-openssl*.patch` | 3.x |
| **libaom** | `0018-libaom-Dont-use-aom_codec_av1_dx_algo.patch` | 4.x |

## When to check this category

- `ERROR: libxxx not found` in configure log
- New library version released that changes API
- Dependency library renamed symbols or headers
- Static vs shared linking detection failures
