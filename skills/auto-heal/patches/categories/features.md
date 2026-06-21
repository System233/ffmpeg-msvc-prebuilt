# Feature Toggles and API Extensions

## Patches

| Patch | Versions | Files | What it does |
|-------|----------|-------|-------------|
| `0040-ffmpeg-add-av_stream_get_first_dts-for-chromium` | 6.x, 7.x, 8.x | `libavformat/avformat.h`, `libavformat/mux_utils.c` | Exports `av_stream_get_first_dts()` function. This accesses the internal `first_dts` field and is needed for Chromium browser integration. Enables linking against FFmpeg for Chromium-based apps. |
| `0022-fix-iconv` | 5.x | `configure` | Prevents libc iconv from being auto-detected when `--disable-autodetect` is used. Iconv would otherwise be silently enabled, breaking the build. |
| `0014-avfilter-dependency-fix` | 4.x | `configure` | Adds explicit `_filter_deps` and `_filter_select` declarations for metadata, headphone, showspatial, superequalizer, surround, and sinc filters that were missing their avformat/avcodec dependencies. |
| `0023-fix-qsv-init` | 4.x, 5.x | `libavcodec/qsv.c` | Uses `MFX_IMPL_VIA_D3D11` when `CONFIG_D3D11VA` is enabled for Intel QSV initialization, instead of the default AUTO path. |
| `0008-fix-sdl2-version` | 3.x | `configure` | Relaxes SDL2 version constraint from `< 2.1.0` to `< 3.0.0` so newer SDL2 is accepted. |

## When to check this category

- Chromium build integration requires specific API exports
- SDL2/ffplay detection fails despite SDL2 being installed
- Auto-detection enabling unwanted features
- QSV hardware acceleration init failures
- Missing avfilter dependencies
