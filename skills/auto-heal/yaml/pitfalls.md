# Common YAML pitfalls

## 1. extends chain broken

**Symptom:** `YAML file not found: ffmpeg/X.Y.yaml`
**Cause:** A YAML references `extends: "X.Y"` but that file doesn't exist.
**Fix:** Create the missing YAML or change `extends` to a valid parent.

## 2. SHA512 mismatch

**Symptom:** `vcpkg_from_github` hash mismatch in CI
**Cause:** `source.sha512` in version YAML doesn't match the upstream tag's tarball.
**Fix:** Update `source.sha512` in `ffmpeg/X.Y.Z.yaml`.

## 3. fnmatch exclusion too broad

**Symptom:** Features unexpectedly missing from build
**Cause:** `exclude: ["post*"]` matches any future feature starting with "post".
**Fix:** Use exact feature names in exclude when possible.

## 4. Version gate syntax error

**Symptom:** Feature silently absent or present when it shouldn't be
**Cause:** Unrecognized operator like `==8.0` or `!=6.0` — only `>=`, `<=`, `>`, `<` work.
**Fix:** Use supported operators only.

## 5. @alias circular reference

**Symptom:** `RecursionError` in Python when generating port
**Cause:** Alias A references alias B which references alias A.
**Fix:** Break the cycle — remove one of the references.

## 6. Feature name typo

**Symptom:** Feature doesn't appear in generated port
**Cause:** `include` references a name not in `base.yaml` features registry.
**Fix:** Check spelling — unknown names are silently ignored.

## 7. fields vs features confusion

**Symptom:** Feature is defined in `define` block but doesn't appear in port
**Cause:** `define` creates alias groups for `include/exclude/defaults`. Actual feature definitions go in `features`. They live in different namespaces.
**Fix:** Ensure the feature name exists in `features:` map in `base.yaml`.

## 8. List replacement (not merge)

**Symptom:** Patches from family YAML disappear in version YAML
**Cause:** `patches` is a list — child **replaces** parent entirely, not merges.
**Fix:** Version YAML must list ALL needed patches, not just the additions.

## 9. `source.sha512` missing in family YAML

**Symptom:** Port generation fails with missing SHA512
**Cause:** Family YAML (e.g., `8.1.yaml`) may not define its own sha512, relying on the version YAML.
**Fix:** Ensure the version YAML provides `source.sha512`.

## 10. `master.yaml` uses `source.ref: "${FFMPEG_REF}"`

**Symptom:** Master build uses wrong ref
**Cause:** The `${FFMPEG_REF}` placeholder requires runtime substitution via `--ref`.
**Fix:** Always pass `--ref` when generating for master.

## 11. dep_overrides version mismatch

**Symptom:** NVENC/CUDA fails on one version but works on another
**Cause:** `nvcodec: "ffnvcodec-11"` exists in 5.x/4.x YAMLs but not in 7.x/8.x.
**Fix:** Check if `dep_overrides` is needed for the version you're fixing.

## 12. Offsets in patch application

**Symptom:** `Hunk #1 succeeded at 7290 (offset 5 lines)` — patch applies but with offset
**Meaning:** Usually fine, but large offsets (>100 lines) signal potential version drift.
**Fix:** If offset grows with each version update, the patch needs refreshing.
