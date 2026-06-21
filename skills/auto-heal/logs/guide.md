# Build Log Reading Guide

## ZIP structure

Log ZIP pattern: `build-logs-{triplet}-{license}-{linkage}.zip`

Example: `build-logs-arm-windows-gpl-shared.zip`

```
detect_compiler/              ← compiler detection (pre-build)
  config-{triplet}-out.log
  config-{triplet}-err.log
  stdout-{triplet}.log

ffmpeg/                       ← main build logs
  stdout-{triplet}.log        ★ START HERE: vcpkg main output
  extract-out.log             source download/extract
  patch-{triplet}-{N}-err.log ★ patch N stderr (only non-empty on issues)
  patch-{triplet}-{N}-out.log patch N stdout
  cmake-get-vars_*-{triplet}* compiler vars
  build-{triplet}-rel-out.log ★★ release build stdout (LARGE: up to 20MB+)
  build-{triplet}-rel-config.log ★ configure log (FFmpeg config.log)
  build-{triplet}-dbg-out.log  debug build stdout (LARGE)
  build-{triplet}-dbg-config.log
  automake-print-lib-out.log
  automake-print-lib-err.log
  libconvert-{triplet}-out.log  DEF→LIB conversion
  copy-tool-dependencies-{N}-*  tool deps
  ...
```

## Reading methodology

### Step 1: Fast failure location

```bash
unzip -p log.zip ffmpeg/stdout-{triplet}.log | grep -i "patch failed\|error:" | tail -30
```

This tells you:
- Which patch failed (e.g., `0042-fix-arm64-linux.patch`)
- Which file it failed on (e.g., `ffbuild/libversion.sh`)
- Whether configure/make produced an error

### Step 2: Get context around the failure

```bash
unzip -p log.zip ffmpeg/stdout-{triplet}.log | tail -50
```

Shows the last steps. If there's no build output, the failure is in patch phase.
If there's build output ending with a compiler/linker error, read more below.

### Step 3: Examine patch failure detail

```bash
unzip -p log.zip ffmpeg/patch-{triplet}-{N}-err.log
```

Replace `{N}` with the patch sequence number from stdout.
Shows exact hunk offset and reject info.

### Step 4: Examine configure error

```bash
unzip -p log.zip ffmpeg/build-{triplet}-rel-config.log | grep -i "error" | tail -50
```

FFmpeg's configure writes ERROR: lines for missing dependencies.

### Step 5: Examine build/compile error

```bash
unzip -p log.zip ffmpeg/build-{triplet}-rel-out.log | grep -ni "error\|fatal\|LNK" | tail -50
```

For very large logs (>5MB), always use grep, never read the whole file.

## Reading the signs

| Observation | Meaning |
|-------------|---------|
| `build-*-rel-out.log` is large | Build started → failure is in compile/link |
| `build-*-rel-out.log` is absent | Failure is in **source download or patch phase** |
| `build-*-rel-out.log` is tiny | Failure is in **configure phase** |
| All patch-err.logs are `0 bytes` | All patches applied cleanly → failure is after patches |
| A patch-err.log has content | Look at the content — "succeeded with offset" = OK, "failed" = BAD |
| `extract-err.log` has content | Source download/extract failed (SHA512 or network) |
