---
name: auto-heal
description: >
  Diagnose and fix CI build failures in ffmpeg-msvc-prebuilt repos,
  both in interactive sessions and via the auto-heal GitHub Action workflow.
  Handles patch application errors, YAML config issues, and vcpkg build log analysis.
  Use when a CI build fails (PR check or auto-heal trigger).
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  workflow: ci-repair
  auto-heal: true
---

## What I do

I fix CI build failures in ffmpeg-msvc-prebuilt. Three entry points:

- **"patch failed" in log** → read `patches/categories/` for the right patch category, read `patches/testing.md` to reproduce
- **build/configure error** → read `logs/guide.md`, then `reference/fix-table.md` for the error signature
- **auto-heal triggered** → read `agent_context.json` in workspace root, identify failed variants, then follow the same decision tree with logs under `error_logs/build-logs-*/`

I also handle YAML misconfiguration: read `yaml/` if the error is in the config chain generation.

## Rules

CRITICAL — I MUST follow these:

- **MUST NOT** modify `scripts/`, `ports/`, `.github/`, `scripts/cmake/`, `data/`, `web/`, `build/`
- **ONLY** modify `ffmpeg/*.yaml` and `patches/*.x/*.patch`.
- **NEVER** modify patches from the main branch. Only PR-added patches (listed in agent_context.json's `new_patches`) may be modified or deleted.
- **MUST NOT** run `vcpkg install`, start servers, or execute commands lasting >30 seconds
- When reading large files (>5MB), use `tail | grep` — never read the whole file
- When testing patches, **MUST apply in YAML patch-list order** — never individually
- **When auto-heal mode**: allowed to run `python scripts/ffport.py`, `git apply`, `pip install -r requirements.txt` for verification. **Still forbidden**: `vcpkg install`, any command likely to exceed 30s.

## Quick Decision Tree

```
┌─ "patch failed" in log ──────────────────────→ patches/categories/ + testing.md
│
├─ "ERROR: libxxx not found" ──────────────────→ patches/categories/dependencies.md
│
├─ "LNK20xx" / "fatal error C" / "nasm" ──────→ patches/categories/msvc-toolchain.md
│                                                 or cross-compile.md
│
├─ YAML parse / "file not found" ──────────────→ yaml/overview.md + pitfalls.md
│
├─ build-*-out.log missing (no build output) ──→ logs/guide.md (patch phase fail)
│
└─ unsure where to start ──────────────────────→ reference/fix-table.md → back to tree
```

## Reference files

| File | When to read |
|------|-------------|
| `reference/cli.md` | Need exact ffport/find_closest_yaml/naming command |
| `reference/fix-table.md` | Need error→root cause→fix direction mapping |
| `logs/guide.md` | Need to decode vcpkg log structure (ZIP for manual, `error_logs/build-logs-*/` for auto-heal) |
| `yaml/overview.md` | Need YAML inheritance chain or field reference |
| `yaml/pitfalls.md` | YAML generates wrong output |
| `patches/index.md` | Need to see which patches exist per version |
| `patches/categories/*.md` | Identified the failure category |
| `patches/testing.md` | Need to reproduce patch failure locally |

## Patch naming rules (for new patches)

When you need to add a new patch:

1. Find the highest existing number in the target version's patch directory
   (e.g., `patches/8.x/` has `0042-xxx.patch` → next number is `0043`)
2. Format: `{NNNN}-{description}-{version-suffix}.patch`
   - `NNNN`: 4-digit zero-padded sequential number
   - `description`: kebab-case description of the fix
   - `version-suffix`: target version (e.g., `8.x`)
3. Add the new patch filename to the version YAML's `patches:` list, in order
4. **Never** reuse an existing number. PR-new patches (from agent_context.json's `new_patches`) can be modified; main branch patches are read-only.

## Auto-heal Mode

When invoked by `.github/workflows/auto-heal.yml`, the following differences apply:

### Log file access

Instead of downloading a ZIP and running `unzip -p`, the workspace already contains:

```
error_logs/
  build-logs-{triplet}-{license}-{linkage}/
    detect_compiler/
      ...
    ffmpeg/
      ...
```

Read the same file names under `ffmpeg/` and `detect_compiler/` as described in `logs/guide.md`, but use direct file reads (e.g. `grep`, `tail`) instead of `unzip -p`.

### Context file

The workflow generates `agent_context.json` at the workspace root containing:

| Field | Description |
|-------|-------------|
| `pr_number` | PR number |
| `failed_jobs` | Array of failed matrix job names (e.g. `"build (x64-windows, gpl, shared)"`) |
| `log_directory` | Always `"./error_logs"` |
| `workflow_url` | Direct link to the failed run |

Also reads `failed_steps_hint.txt` for a quick list of failed step names.

### Flow

1. Read `agent_context.json` → identify failed matrix variants
2. Find corresponding `error_logs/build-logs-{triplet}-{license}-{linkage}/`
3. Examine `ffmpeg/stdout-{triplet}.log` for first error (as described in `logs/guide.md`)
4. Follow the same decision tree under "## Quick Decision Tree"
5. Fix → verify:
   - YAML changed → `python scripts/ffport.py generate <version>`
   - Patches changed → `git apply --check` in YAML patch-list order
   **Only `new_patches` from agent_context.json may be modified; main branch patches are read-only.**
6. Exit
