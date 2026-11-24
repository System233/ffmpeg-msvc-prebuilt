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

The generated Overlay lives under `_work/ffbuild/generated-ports/`.
It contains one directory per source-backed FFmpeg release (`ffmpeg-8-1-3`,
`ffmpeg-9-1`, etc.) and a shared virtual `ffmpeg-deps` Seed. As of November
2026 there are 26 source-backed releases and three YAML-only inheritance
templates. Every generated FFmpeg directory has **`name: ffmpeg`** in its
vcpkg manifest. The directory names select source versions; they are **not**
distinct vcpkg package names.

Never pass the `generated-ports/` parent as an Overlay for FFmpeg installation
or native ABI scanning. Pass the selected **single Port directory**. The one
original `ports/ffmpeg-tester` remains unchanged and depends on `ffmpeg`.
Different FFmpeg versions cannot coexist within one installed Triplet tree.

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
Generated Port self-dependencies continue to reference `ffmpeg`; the original
Tester references `ffmpeg` without any versioned Consumer Port.

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
passes no production Secrets, always uses `dry_run` and `skip_publish`, and
uses `skip_release: false` so real MSVC Consumer builds and Release ZIP
packaging are both tested. A second independent publication guard prevents
*any* `ci/` ref from entering the production publish job even if inputs are
accidentally changed.

The final isolated regression smoke adds four complementary families:
5.1.10 (x64/LGPL/static), 7.1.5 (ARM/GPL/shared),
8.0.1 (ARM64/GPL/shared), and 9.0.2 (x86/LGPL/static), using a 16-way
shard of each release's ABI-sorted variants. Earlier real CI already
verified 3.4.14 x64/shared, 4.4.8 ARM/static, 6.1.6 x86/shared, and
9.1 ARM64/static. No 8.1.x reruns, full historical matrices,
production PRs or Release/data publication are required.

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
   writes on a space-constrained Windows Runner. **Before building, the Worker
   queries vcpkg's native ABI graph including the FFmpeg Consumer Tester and
   requires a nonempty files-provider ZIP for every third-party ABI**; missing
   dependency packages are fatal rather than locally compiled. **After building,
   the Worker checks buildtree logs**, failing if any third-party Port was
   compiled despite the preflight. Only the selected FFmpeg Port and its Tester
   may build in the Worker.

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
using `ffmpeg[...]`; the scanner selects the matching version-directory
Overlay while the native package identity remains `ffmpeg`. **Each variant
is queried in its own vcpkg plan**, even though all Port definitions have
already been generated together. Combining different
FFmpeg versions into one vcpkg install plan could merge Features of their
shared dependencies, returning ABIs different from their isolated builds.

The scanner **runs** `vcpkg install --dry-run`: no FFmpeg or dependency Port
is built or installed, but vcpkg can invoke CMake and compile compiler-ID
probes when computing the triplet ABI. For each requested version/Triplet/Feature profile, the scanner reads vcpkg's actual
dependency graph and ABI hash, not another Python dependency hash. Missing
native ABI output is a hard error, never a reason to substitute a fake hash.

The scan output (`schema: 3`) contains `port`, `package`, `abi_hash`,
`triplet`, `features`, `version`, `release_date`, and Master source information.
The Planner compares the **full** `abi_hash` with published `data` records.
Historical records without a native ABI remain readable but cannot silently
satisfy a native-ABI deduplication check.

## Build one selected version (Windows/MSVC)

```powershell
python -m ffvcpkg install "ffmpeg[all-lgpl,static]" ffmpeg-tester `
  --triplet=x64-windows `
  --overlay-ports=_work/ffbuild/generated-ports/ffmpeg-8-1-3 `
  --overlay-ports=ports
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
after building `ffmpeg` from the selected version-directory Port. The
packager checks the actual installed Feature selection, upstream source
version, Triplet, linkage and licensing policy. The **Static Binary ZIP
contains executables only**, plus build metadata and the license; it does NOT
copy libraries or headers. Shared Binary/Develop SDK archives preserve the
original layout. Crucially, the packager verifies the **actual packaged
vcpkg ABI input file** at `share/ffmpeg/vcpkg_abi_info.txt` and refuses to publish if its SHA256 differs
from the proposed pre-build ABI. The dry-run ABI is only the proposal, not
independent evidence that the package was built with those inputs.

Package-format v2 also requires the Worker-installed vcpkg root and unpacked
FFmpeg source (`--installed-root`, `--buildtrees` or `--source-tree`).
It enumerates dependency packages actually installed and reachable from
FFmpeg's status records, copies reachable Port copyright and original SPDX,
and includes upstream COPYING terms. Missing evidence fails packaging. For native vcpkg SPDX, the installed
binary and Port recipe entries carry the calculated manifest/feature
license in licenseConcluded (licenseDeclared is NOASSERTION).
The consolidated evidence preserves the source field and rejects unknown
primary assertions, inconsistent identities or conflicting expressions.
Original source-resource entries remain in the unmodified per-Port SPDX.
An explicitly null Port license can be resolved only with reviewed evidence:
pkgconf 2.5.1 uses a custom permissive copyright text verified byte-for-byte
against upstream COPYING. Its exact SHA-256 is pinned and the SBOM contains
a LicenseRef with the full extracted text. Unknown or altered notices still
fail closed; no package-name-only exemption is used.
Binary and Develop ZIPs contain LICENSES/THIRD_PARTY_NOTICES.md,
metadata/SBOM.spdx.json and metadata/BUILD_PROVENANCE.json.
No independent compliance ZIP, SBOM, checksum or YAML is published.
Static retains its executable-only binary payload.

The compatibility gate uses license-expression (SPDX AND/OR/WITH) and an
explicit, versioned policy in ffbuild/license_policy.py. The actual FFmpeg
GNU license from copyright determines the permitted GNU profile, without
silently upgrading it. AND requires every selected branch to be compatible;
OR records one complete compatible alternative; WITH requires scope-specific
review unless an independent compatible OR branch is available. Unknown
licenses and unreviewed custom references block target publication.
LGPL library linking remains conditional on each library's own source and
relink obligations; it is not a grant to merge source or a legal certification.
Native status dependency edges retain name and triplet. Root manifest host
flags and explicitly cross-triplet x64 host edges identify build-only paths;
any target path dominates. Same-triplet transitive host flags are accepted
only from the matching Port manifest whose SHA-256 is recorded by vcpkg in
its original SPDX. Only relevant manifest evidence is retained in provenance;
unproven roles are target candidates. Build-only tools still require license evidence, but
their copyleft terms do not by themselves determine target linkage licensing.
The ZIP records policy version, actual license profile, scope, and selected
license terms. Publication recomputes decisions from original evidence;
ABI reuse requires the current policy version. See SPDX 2.3 Annex D and
the GNU license list and GPL FAQ for the rule basis. The internal
license_reviews.yaml registry supports scoped approval of unknown atoms or
WITH exceptions: exact installed package version/revision, copyright SHA-256,
complete expression, GNU profile, linkage and review source/reason. Explicit
policy denials cannot be overridden. Update POLICY_VERSION when rules change.


The scan pins a UTC date shared by the build plan. Public filenames use
ffmpeg-{version}_{triplet}-{linkage}-{license}[-develop]-YYMMDD.zip;
master uses master as the public version. The release tag is
ffmpeg-{version}-YYMMDD. Internally, full native ABI drives scheduling and
archive SHA-256 verifies delivery. Unchanged variants are downloaded from
their earlier Release, verified, and reused without renaming or recompiling.
If all required ABIs already exist but the latest published matrix is different,
the publisher assembles a new complete Release without any compile jobs.
Each build worker runs the read-only publication gate before uploading its
CI artifact. New dated releases are staged as drafts until all assets are
verified.
An already published dated release cannot be overwritten; same-day changes
must be deferred or handled by an explicitly separate publication policy.

These materials identify the *installed dependency graph*, not necessarily
the exact object files linked into each executable. They do not by themselves
fulfill every source-distribution or LGPL relinking obligation; final legal
compatibility, including disputed historical components, requires review.

Native records keep an internal ABI-qualified CI identifier and the full
abi_hash. Public archive names have no ABI suffix. Dated variant records
remain under the existing family/version-date/variants layout. Historical
records without dated compliance evidence are retained but not reused.

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

Earlier isolated native MSVC builds validated eight distinct version/Triplet
combinations using the pre-v2 archive layout. Package-format v2 and its
new fail-closed license gates require a separate end-to-end smoke before
being considered production-ready; offline tests alone are insufficient.


### Supplemental license declarations

The root `licenses/` directory contains one standard SPDX 2.3 JSON document
per Port with missing metadata. The package `versionInfo` follows vcpkg
(version plus #port-version if nonzero), `licenseConcluded` records our
conclusion, `licenseDeclared` remains NOASSERTION, and `sourceInfo` and
`licenseComments` retain the evidence source and scope. Nonstandard terms
carry their actual text in `hasExtractedLicensingInfos`. Unresolved
terms remain NOASSERTION and block packaging. Original SPDX/copyright files
remain in the ZIP; the applied SPDX document is recorded in build
provenance. Native known/conflicting/partially unknown expressions are not
overwritten. Existing exact-copyright pkgconf approval remains scoped.
No third-party Port or vcpkg ABI changes are needed.

A correction to a known native expression is allowed only when the local SPDX package's licenseDeclared matches the same SPDX syntax tree (ignoring AND/OR ordering), the Port version matches, and the installed copyright SHA256 matches the SPDX file checksum. The original SPDX is preserved; the normal compatibility gate still applies. glslang is the initial correction.

The reviewed Windows opengl SDK import-only Port is classified as an external system dependency only when its native SPDX has the exact reviewed recipe checksum, matching SDK notice and import-only installed payload. Its license remains NOASSERTION; SDK headers, import libraries and DLLs themselves are prohibited in release archives. Unknown system packages are not exempted.
