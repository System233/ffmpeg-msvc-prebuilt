# YAML Configuration System

## Inheritance chain

```
base.yaml          ← Feature registry (NEVER modify existing entries)
  ↑ extends
X.Y.yaml           ← Family config: source ref, build options, feature selection
  ↑ extends
X.Y.Z.yaml         ← Version config: sha512, patches list, revision
```

Example chain for `8.1.1`:
```
base.yaml → 8.0.yaml → 8.1.yaml → 8.1.1.yaml
```

## Field reference: base.yaml

| Field | Type | Description |
|-------|------|-------------|
| `features.<name>.flag` | string | FFmpeg configure `--enable-*` flag(s) |
| `features.<name>.pkgconfig` | string | pkg-config module name (core libs only) |
| `features.<name>.description` | string | Human-readable description |
| `features.<name>.depends` | string/list | vcpkg deps (plain string) or feature refs (`@name`) or dict with platform |
| `features.<name>.platform` | string | Platform constraint (`"!uwp"`, `"!x86 & !arm32 & !uwp"`) |
| `features.<name>.version` | string | Version gate (`">=4.2"`, `"<5.0"`, `">=6.0 <8.0, >=9.0"`) |
| `define` | map | Alias groups: `include`, `exclude`, `defaults`, named groups like `core`, `all`, `lgpl` |

## Field reference: family YAML (X.Y.yaml)

| Field | Type | Description |
|-------|------|-------------|
| `extends` | string | Parent (`"base"` or `"X.Y"`) |
| `source.method` | string | `"git"` or `"url"` |
| `source.repo` | string | GitHub repo (`"ffmpeg/ffmpeg"`) |
| `source.ref` | string | Git ref (`"n${VERSION}"` with placeholder) |
| `source.sha512` | string | Source SHA512 (128 hex) |
| `build.base_options` | string | Base configure options |
| `build.debug.options` | string | Debug configure options |
| `build.release.options` | string | Release configure options |
| `build.host_deps` | list | Host dependencies (name + host:true) |
| `build.cmake_defines` | map | CMake variables (`FFMPEG_NEED_BIN2C: "ON"`) |
| `dep_overrides` | map | Feature → alternative vcpkg dep name |
| `features` | map | Override feature definitions from base.yaml (rare) |
| `define.include` | list | Features to include |
| `define.exclude` | list | Features to exclude (supports fnmatch) |
| `define.defaults` | list | Default features |

## Field reference: version YAML (X.Y.Z.yaml)

| Field | Type | Description |
|-------|------|-------------|
| `extends` | string | Parent family (`"X.Y"`) |
| `revision` | int | Port revision (bump to trigger rebuild) |
| `source.sha512` | string | Source SHA512 for this exact version |
| `patches` | list | Patch file paths relative to `patches/` (e.g. `"8.x/0002-fix-msvc-link-8.1.patch"`) |

## Merge rules

| Field type | Rule | Example |
|-----------|------|---------|
| dict | Deep recursive merge | `source`, `build`, `features`, `define` |
| list | Complete replacement | `patches`, `host_deps` (child replaces parent entirely) |
| scalar | Override | `revision`, `source.sha512` |
| `null` | Delete key | Setting a field to `null` removes it from parent |

## Version gate syntax

- `>=6.1`, `<5.0`, `>4.0`, `<=7.0` — standard comparison
- Comma `,` = OR: `>=6.0 <8.0, >=9.0` matches 6.x-7.x OR 9.x+
- Space = AND within a group: `>=6.0 <8.0` matches 6.x-7.x only
- Non-numeric or unrecognized → feature silently excluded

## All version YAMLs and their inheritance

| YAML | extends | Chain |
|------|---------|-------|
| `master.yaml` | `8.1` | `base → 8.1 → master` |
| `8.1.1.yaml` | `8.1` | `base → 8.1 → 8.1.1` |
| `8.1.yaml` | `base` | `base → 8.1` |
| `8.0.1.yaml` | `8.0` | `base → 8.0 → 8.0.1` |
| `8.0.yaml` | `base` | `base → 8.0` |
| `7.1.2.yaml` | `7.1` | `base → 7.1 → 7.1.2` |
| `7.1.1.yaml` | `7.1` | `base → 7.1 → 7.1.1` |
| `7.1.yaml` | `base` | `base → 7.1` |
| `7.0.2.yaml` | `7.0` | `base → 7.0 → 7.0.2` |
| `7.0.yaml` | `base` | `base → 7.0` |
| `6.1.1.yaml` | `6.1` | `base → 6.1 → 6.1.1` |
| `6.1.yaml` | `base` | `base → 6.1` |
| `5.1.2.yaml` | `5.1` | `base → 5.1 → 5.1.2` |
| `5.1.yaml` | `base` | `base → 5.1` |
| `4.4.7.yaml` | `4.4` | `base → 4.4 → 4.4.7` |
| `4.4.yaml` | `base` | `base → 4.4` |
| `3.4.14.yaml` | `3.4` | `base → 3.4 → 3.4.14` |
| `3.4.yaml` | `base` | `base → 3.4` |
