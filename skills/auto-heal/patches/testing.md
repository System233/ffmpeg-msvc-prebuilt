# Offline Patch Testing

This procedure tests patches in the **same sequential order** vcpkg applies them, without needing a vcpkg environment.

## Prerequisites

- Python 3.x + pyyaml (`pip install -r requirements.txt`)
- `git` available on PATH
- The failing version's YAML chain must be valid

## Procedure

### Step 1: Get the exact source

Determine the version from the failing CI log (`Downloading https://.../ffmpeg-ffmpeg-n{VERSION}.tar.gz`).

```bash
curl -L "https://github.com/ffmpeg/ffmpeg/archive/n{VERSION}.tar.gz" -o src.tar.gz
tar -xzf src.tar.gz
cd ffmpeg-n{VERSION}
git init && git add -A && git commit -m "base"
```

### Step 2: Get patch list in order

Read the YAML to get the ordered patch list. The version YAML's `patches:` field lists them in application order:

```yaml
# ffmpeg/8.1.1.yaml
patches:
  - 8.x/0002-fix-msvc-link-8.1.patch
  - 8.x/0003-fix-windowsinclude.patch
  # ...
```

### Step 3: Apply patches sequentially

```bash
set -e  # stop at first failure
for patch in \
    patches/8.x/0002-fix-msvc-link-8.1.patch \
    patches/8.x/0003-fix-windowsinclude.patch \
    # ...
do
    echo "=== Applying $patch ==="
    if git apply --check "$patch"; then
        git apply "$patch"
        echo "OK"
    else
        echo "FAILED: $patch"
        git apply --reject "$patch" 2>&1 || true
        break
    fi
done
```

### Step 4: Interpret results

| Outcome | Meaning | Next step |
|---------|---------|-----------|
| All patches apply cleanly | Patch phase is fine → check configure/build later | Read `logs/guide.md` for build errors |
| Patch fails with `Hunk #N succeeded at ... (offset M lines)` | Patch applies but context shifted. Small offset (<20) is OK; large offset (>100) signals drift | For large offset, consider refreshing the patch |
| Patch fails with `patch failed: file:N` | Patch cannot apply. Version drift | Fix the patch or remove it |
| `.rej` files generated | Partial failure. Some hunks applied, some didn't | Manually merge the `.rej` content |

## Quick check (for known failing patch)

If you already know which patch fails and just want to test that one:

```bash
cd ffmpeg-n{VERSION}
git init && git add -A && git commit -m "base"
git apply --check ../patches/{major}.x/{patch-name}.patch
```

Exit code 0 = applies cleanly. Non-zero = fails.

## Key notes

- **DO NOT** skip patches before the failing one — earlier patches may change files that later patches depend on
- **DO NOT** apply patches individually in isolation — the order matters
- Some patches apply with `offset` (hunk line shift). This is normal as long as it succeeds
- The `/l` at end of some patch lines (`toupper(){?`) is git's representation of trailing whitespace in the source
