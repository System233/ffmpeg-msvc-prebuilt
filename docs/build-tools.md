# FFmpeg build tools: native vcpkg ABI planning

`ffbuild` generates version-qualified FFmpeg overlay ports, queries the ABI
computed by **vcpkg itself**, filters already published variants in the local
`data` branch checkout, and packages/publishes successful builds.

No Python recipe/feature hash is used by the production planning path. Compiler
and SDK fingerprints are not implemented independently: vcpkg owns its own ABI
algorithm and binary cache. This does not override any environment inputs
that vcpkg itself includes in an ABI.

## Generate all versions

```powershell
python -m ffbuild generate --all
```

The generated Overlay lives under `_work/ffbuild/generated-ports/`. The
generator creates all source-backed stable FFmpeg releases plus a matching
`ffmpeg-tester-<version>` Port for each, and one shared virtual `ffmpeg-deps`
dependency Seed. As of November 2026 there are 26
source-backed releases and three YAML-only inheritance templates; templates
are not independent Ports.

Each vcpkg Port name is distinct: `ffmpeg-8-1-3`, `ffmpeg-9-1`, etc.
The installed FFmpeg filesystem layout is **not** renamed: multiple versions
are not promised to coexist inside one installed Triplet tree.

An optional pinned Master snapshot can be generated in the same pass:

```powershell
python -m ffbuild generate --all --include-master `
  --describe n9.1-12-gabcdef0 --commit <full-40-character-commit> `
  --sha512 <source-tarball-sha512>
```

Without explicit pinned arguments `--include-master` discovers upstream HEAD,
pins its Commit and computes the source tarball SHA512. The dedicated Master
workflow passes pinned metadata from its source-discovery job; the daily
release rotation can also pin Master during generation.

The original authored Overlay Ports in `ports/` and everything in `scripts/`
are left untouched. **Version-qualified FFmpeg Ports copy the existing
`scripts/cmake/ffmpeg-portfile.cmake` builder and its `build.sh.in`, CMake
consumer support and usage files byte-for-byte**; the generated `portfile.cmake`
only supplies version, source checksum/ref, patch list, feature flags and
existing CMake definitions. ARM/MSVC SDK workarounds, CRT/debug flags, GAS
preprocessing, dependency link paths, FFmpeg installation and pkg-config
fixups remain implemented in the original builder, not reauthored. Each Port
also generates the existing license/feature policy as `constraints.cmake`.
Generated Port self-dependencies and tester dependencies point to the
corresponding version-qualified Port.

Offline regression tests compare the original builder files, source-patch
bytes/order, feature-macro mappings and host tool options for **every**
source-backed release. A change to the original builder must therefore be
reflected in every generated Port without silently dropping its behavior.

## CI completeness and recovery contracts

- **Published releases are intentionally paced.** The UTC daily schedule
  selects exactly **one** source-backed FFmpeg version from a deterministic
  27-day cycle (26 stable versions plus pinned upstream Master as of November
  2026). Each daily run scans at most 16 ABI variants for its one version;
  published matching ABIs are skipped. The complete roster is revisited over
  time instead of producing a daily 160/416-job matrix. The separate weekly
  Master schedule is disabled because Master participates in this same cycle.
- Main-branch Push and PR scan **all impacted source-backed releases**,
  including historical patch versions, strictly for validation (`dry_run`).
  These events do **not** publish GitHub Releases. Source or workflow changes
  that affect the build pipeline conservatively validate all affected versions
  and the pinned Master snapshot when relevant. Explicit manual publication
  requires a single version and refuses whole-history / partial shard plans.
- FFmpeg 3.4 OpenSSL's explicit nonfree requirement is excluded from inherited
  LGPL/GPL aggregate profiles. It is reachable only through the explicitly
  selected nonfree aggregate. Target policy errors are fatal to CI planning:
  no successful matrix may quietly omit a declared preset.
- The complete native ABI plan remains one immutable artifact. Large PR/Push
  validation may still use **two matrices of up to 256 jobs** each. Regular
  Release builds are capped at one version (16 declared variants), not two
  historical matrices. More than 512 validation jobs fail planning rather
  than silently truncate. Manual sharding remains a validation mechanism,
  not a release scheduling or ABI scan-cost optimization.
- Manual runs support `force` to rebuild even if the same ABI is already
  published. Forced verification builds do **not** automatically republish
  potentially nonidentical assets under an immutable ABI name.
- GitHub Release publication is idempotent: create an empty release tag, list
  existing assets, verify matching sizes and SHA-256 digests (download the
  existing asset if GitHub does not expose a digest), and upload **only**
  missing assets. Conflicting immutable assets are fatal; there is no clobber.
  The data branch is updated only after all required uploads are confirmed.
- Normal PR validation must succeed explicitly. For Auto-Heal PRs, the
  version-scope security check must also succeed explicitly; skipped checks
  are not accepted as evidence that the patch is within its allowed scope.

## Isolated GitHub CI smoke (without Release or publication)

The reusable `build-release.yml` accepts two independent CI inputs:

- `skip_release: true` keeps the native ABI check, static dependency Seed,
  real FFmpeg compilation and the vcpkg consumer test, but skips creation and
  uploading of Release ZIP archives and `.var.yaml` metadata.
- `skip_publish: true` skips the entire GitHub Release and `data` branch
  publication job. These controls are available in both reusable and manually
  dispatched build workflows; production defaults remain `false`.

The dedicated `.github/workflows/ci-e2e.yml` runs **only on pushes to
`ci/e2e-*`** and deliberately uses a workflow name not subscribed to by the
production Auto-Heal `workflow_run` trigger. It grants only read permissions,
passes no production Secrets, always uses `dry_run`, and enables both skip
switches. A second independent publication guard prevents *any* `ci/` ref
from entering the production publish job even if inputs are accidentally
changed.

Initial smoke runs one native build worker: FFmpeg 8.1.3, x64-windows,
LGPL/static, selected as index 10 from the stable native-ABI-sorted 16-job
plan (shard_count=16). Set `skip_release: false` in the CI-only test workflow
for a separate packaging test while keeping `skip_publish: true` and
`dry_run: true`. Do **not** create a production PR from the test branch: it
would trigger unrelated PR jobs.

## Shared dependency prebuild and CI caches

The original CI optimization is retained: third-party dependency libraries
are **statically linked** and prebuilt once per Triplet before independent
FFmpeg Workers start. Dependency DLLs are **not** collected or packaged as
Release artifacts; only FFmpeg Port outputs are packaged. Versioned FFmpeg
Ports do not imply version-specific copies of identical dependencies.

The generated `ffmpeg-deps` Port has an `all` feature containing the compatible
external libraries, with alternative dependency names in separate features.
Its dependencies are derived from the actual compiled feature definitions for
every source-backed FFmpeg version, including platform expressions, version
overrides and host tools. The original mutual-exclusion groups (`ffnvcodec`,
`ffnvcodec-11`, `libvpl`, `mfx-dispatch`) are preserved. Individual profiles
use separate temporary install roots so vcpkg never combines conflicting
features into one dependency graph.

CI's work order is:

1. `plan` generates all versioned Ports and `ffmpeg-deps`, but only scans
   the **one selected release version** during scheduled/manual publication;
   it outputs only the Triplets with unpublished native ABI work. The ARM SDK
   selection workaround is applied **before** the ABI scan, matching Prepare
   and Build runners so the planned compiler ABI does not depend on a different
   SDK selection.
2. `download` restores a shared vcpkg downloads cache, or runs `ffbuild prepare
   --triplet <triplet> --only-downloads` once across all four architectures and
   saves the consolidated downloads. Previously published download caches are
   used as fallback sources.
3. `prepare` runs once per **needed Triplet**, restoring a prior binary Seed
   when possible. Otherwise it runs `ffbuild prepare --triplet <triplet>` and
   saves a consolidated native vcpkg binary cache under a new immutable key.
4. Each `build` Worker restores the **exact same completed Seed key, read-only
   from GitHub Actions**. A missing cache fails the job instead of silently
   rebuilding all dependencies independently. The worker vcpkg binary source
   itself is `read` rather than `readwrite`, preventing redundant FFmpeg ZIP
   writes on a space-constrained Windows Runner. vcpkg still validates each
   package's actual ABI and may build a missing variant locally in the Worker.

The cache namespace is scoped by pinned vcpkg version, Triplet and the
generated Seed plus authored Port and Triplet inputs. Old `ffbuild-seed`,
`ffbuild-native` and `vcpkg-seed` entries can supply existing binaries when
preparing a new Seed; only `prepare` writes the consolidated GitHub cache.
There is no independent compilation-environment fingerprint.

Seed builds use `--clean-buildtrees-after-build` and
`--clean-packages-after-build`, **not** `--clean-after-build`: the latter also
deletes the downloads cache. All these commands run on Windows CI, never as
part of local Python tests or `generate --all`.

## Scan native ABIs without compiling

The CI uses pinned vcpkg 2026.06.01. Its `install --dry-run` command supports
the experimental `--x-write-nuget-packages-config=<path>` option. The resulting
NuGet `packages.config` gives each Port's full native ABI in its
`<version>-vcpkg<sha256>` package version.

```powershell
python -m ffbuild scan --version 8.1.3 --output ffbuild-abi.json
python -m ffbuild plan --abi-file ffbuild-abi.json --state-dir data
```

Use `scan --history` for every source-backed stable release; the default
without `--version` selects the latest release in each family, while the
generator still prepares *all* versions. `scan --targets-file <yaml>` selects
other native Package Specs/Triplets. The target declaration lists profiles
using `ffmpeg[...]`; the scanner maps each to the matching version-qualified
Port. **Each variant is queried in its own vcpkg plan**, even though all
Port definitions have already been generated together. Combining different
FFmpeg versions into one vcpkg install plan could merge Features of their
shared dependencies, returning ABIs different from their isolated builds.

The scanner **runs** `vcpkg install --dry-run`: no FFmpeg or dependency Port
is built or installed, but vcpkg can invoke CMake and compile compiler-ID
probes when computing the triplet ABI. For each requested version/Triplet/Feature profile, the scanner reads vcpkg's actual
dependency graph and ABI hash, not another Python dependency hash. Missing
native ABI output is a hard error, never a reason to substitute a fake hash.

The scan output (`schema: 3`) contains `port`, `package`, `abi_hash`,
`triplet`, `features`, `version`, `revision`, and Master source information.
The Planner compares the **full** `abi_hash` with published `data` records.
Historical records without a native ABI remain readable but cannot silently
satisfy a native-ABI deduplication check.

## Build one selected version (Windows/MSVC)

```powershell
python -m ffvcpkg install "ffmpeg-8-1-3[all-lgpl,static]" `
  ffmpeg-tester-8-1-3 --triplet=x64-windows
```

Each CI build runs on an isolated Windows Runner, so two different FFmpeg
versions never install their overlapping include/library paths in one tree.
The generated Overlay is uploaded once from CI planning and restored in each
build Worker. Before installation the Worker repeats the read-only ABI query
for its target; it fails if its native ABI differs from the planned ABI.

The centrally prebuilt native vcpkg binary cache remains active for dependency reuse; `data`
tracks **published artifacts**, not whether a package is present in cache.

## Package, data and publish

The CI executes `ffbuild package --job-env FFBUILD_JOB --port-dir <package-dir>`
after building the exact versioned Port. The packager checks the actual
installed Feature selection, upstream source version, Triplet, linkage and
licensing policy; a static archive includes libraries and headers. Crucially,
the packager also verifies the **actual packaged vcpkg ABI input file** at
`share/<port>/vcpkg_abi_info.txt` and refuses to publish if its SHA256 differs
from the proposed pre-build ABI. The dry-run ABI is only the proposal, not
independent evidence that the package was built with those inputs.

Native records use `-a<12-character ABI prefix>` in their variant names and
store their full `abi_hash`, Port name and actual Package Spec. The Release
Tag remains version-based, so multiple build ABIs can be added as different
assets without overwriting an older archive. The public `data` branch remains
the publishing database and is never fetched implicitly by `scan` or `plan`.

`ffbuild publish` verifies the plan and archive digests, creates or uploads
assets to GitHub Release, then writes the variant and version index YAML into
the local `data` checkout and commits/pushes that branch. `--dry-run` only
validates local assets; it does not upload or update the database. Nonfree
artifacts are prohibited from publication. Existing GitHub Release assets are
not uploaded with `--clobber`.

## Legacy data and versioning

Legacy variant YAMLs containing only license/linkage labels (or independent
Recipe/Feature hashes) are preserved for historical access. They do not claim
to contain a native ABI and are not used for ABI deduplication. New native
records are additive. Version indexes retain old entries and count only
native-ABI records toward native build completion.

The native NuGet ABI export is **experimental** in vcpkg. It was tested
against the pinned 2026.06.01 registry/tool on Windows: repeat scans are
stable; changing a selected Feature changes the target ABI; changing a
dependency recipe changes both the dependency ABI and the dependent ABI;
restoring the recipe restores the original hashes. A real minimal package
installation reported exactly the ABI calculated beforehand.

FFmpeg production MSVC builds and live GitHub publication still require their
separate end-to-end CI validation. No local mock claims to have completed them.
