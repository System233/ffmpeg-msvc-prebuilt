# FFmpeg build tools: native vcpkg ABI planning

The repository uses a single Python toolchain under scripts/ffbuild and scripts/ffvcpkg.
Install it from the repository root: python -m pip install -e .
Both python -m ffbuild and python -m ffvcpkg remain supported; console scripts are also installed.
The tools are checkout-bound; generated ports, patches and CMake templates remain in this repository.


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
workflow stores the pinned metadata in the immutable attempt-specific source artifact and Build Plan.
The exact same source is used by all build jobs and its automatic repair PR.

Existing authored Overlay Ports and CMake support are reused, with explicit
source-compatibility and license corrections. **Version-qualified FFmpeg Ports copy the existing
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

- Main Push and ordinary PRs run only Ubuntu validation and unit tests.
  No Windows ABI scan, dependency Seed, or FFmpeg compilation runs.
- Only same-repository PRs created by the authorized GitHub App Bot with
  matching `version:<version>` labels and version-specific branches can
  compile. Their cumulative diff must preserve every other version's
  resolved recipe, inheritance and patch bytes. They validate all 16
  targets for exactly one version, without publishing.
- The single daily workflow discovers upstream stable versions and creates
  missing labeled PRs. Weekly Friday (06:00 UTC) directly requests a Master
  build. There is no stable-version daily rotation.
- Production builds are requested on main through `Build FFmpeg Release`
  workflow_dispatch with one required YAML version, or the weekly Master
  caller. A source pin and exact repository commit are recorded before
  native compilation. A complete-run retry retains the original pin/date.
  Tag pushes never trigger builds. New-version and repair PRs end at merge.
- Only after the entire build matrix and reused ZIPs have been validated does
  the publisher allocate `ffmpeg-<version>-YYMMDD` (same-day distinct
  verified batches use `R2`, `R3`, etc.) and create an annotated tag at the
  exact built repository commit. The annotation binds the verified batch
  identity, allowing an identical batch to resume a failed upload. No tag
  is created for a failed build, unchanged ABI matrix or validation-only PR.
  Draft Release upload is independently verified before public release.
  An upload failure can retain a verified tag and draft for recovery.
  ZIP filenames retain the original date format.
- FFmpeg 3.4 OpenSSL's explicit nonfree requirement is excluded from inherited
  LGPL/GPL aggregate profiles. It is reachable only through the explicitly
  selected nonfree aggregate. Target policy errors are fatal to CI planning:
  no successful matrix may quietly omit a declared preset.
- The native ABI plan is one immutable artifact and contains at most 16
  standard target variants for a single production version. Only missing
  native ABIs are built on a production request; authorized Bot PRs force verification of
  the complete target matrix. The CI output rejects plans larger than 16
  jobs or containing more than one version; local JSON planning remains unrestricted.
- Agent repair is read-only with respect to GitHub. It must run
  `python -m ffbuild autoheal check-worktree` before and after committing.
  The same version scope is independently checked during delivery and PR
  validation. Illegal changes are repaired inside the current Agent session;
  a premature exit resumes that session, rather than resetting its work.
- GitHub Release publication is idempotent: create a draft for an existing verified tag, list
  existing assets, verify matching sizes and SHA-256 digests (download the
  existing asset if GitHub does not expose a digest), and upload **only**
  missing assets. Conflicting immutable assets are fatal; there is no clobber.
  The data branch is updated only after all required uploads are confirmed.
- Normal PR validation must succeed explicitly. For Auto-Heal PRs, the
  version-scope security check must also succeed explicitly; skipped checks
  are not accepted as evidence that the patch is within its allowed scope.

## Validation without publication

The reusable build workflow accepts explicit validation-only controls for
authorized Bot PRs: dry_run, force, skip_publish and skip_release. Ordinary
branch pushes cannot use this entrypoint to run native builds. The temporary
branch-driven E2E workflow is not part of the production tree. Any additional
remote smoke harness belongs on an isolated, separately reviewed test branch.

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
   the **one selected release version** for a production request or automatic PR;
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
copy libraries or headers. Shared Binary provides the Release SDK; Debug is a differential add-on containing Release PDBs and Debug libraries/symbols. Crucially, the packager verifies the **actual packaged
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
All public ZIPs have one share namespace, `share/ffmpeg/`, with a combined
`copyright` (the unmodified applicable FFmpeg GNU terms and target-candidate
Port notices, separated by component headers) and `sbom.spdx.json` (one
SPDX 2.3 installed dependency graph). `LICENSE.txt` retains the original
FFmpeg primary license. Verified build-only and external system notices are
not included in the combined copyright; their roles remain in SPDX and the
internal audit. No `LICENSES/`, `metadata/`, `CONTROL`, `BUILD_INFO`,
`vcpkg.spdx.json` or `vcpkg_abi_info.txt` is distributed. Static retains its
executable-only binary payload; Shared Binary retains consumer metadata; Debug contains only the differential debug payload.
Before upload, Windows x64/x86 Workers extract the actual public ZIPs, run
the CLI, and compile/link/run three CMake consumer modes (full, demand and
legacy) in both configurations. Shared Binary is verified alone and then
with the matching Debug overlay in the same build tree; DLL deployment,
configuration-specific import paths and pkg-config roots are checked.
ARM/ARM64 remain covered by native cross-compilation, archive layout and
PDB identity checks; x64-host execution is not claimed for these targets.

One internal `<variant>.audit.zip` accompanies the CI artifact (not a public
Release asset). It holds the original per-Port notices/SPDX, upstream COPYING,
ABI inputs and provenance bound to the exact public archive digests. The
publisher independently rechecks the evidence and reproduces both public
license files. The audit archive remains in the finite-retention CI artifact
only; no audit archive, SPDX, provenance, or compliance report is written to
Data. Data is a Release index containing only published variant metadata,
asset names, sizes, digests and archive format. Reuse verifies exact indexed
ZIP bytes and current package format, without needing expired CI artifacts.
No independent compliance ZIP, SBOM, checksum or YAML is published as a
GitHub Release asset.

The compatibility gate uses license-expression (SPDX AND/OR/WITH) and an
explicit, versioned policy in scripts/ffbuild/license_policy.py. The actual FFmpeg
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
The CI audit records policy version, actual license profile, scope, and selected
license terms. Fresh publication recomputes decisions from original evidence;
ABI reuse requires the current publication format and original archive digest.
Policy changes must advance the publication format; no independent policy
record is stored in Data. See SPDX 2.3 Annex D and
the GNU license list and GPL FAQ for the rule basis. The internal
license_reviews.yaml registry supports scoped approval of unknown atoms or
WITH exceptions: exact installed package version/revision, copyright SHA-256,
complete expression, GNU profile, linkage and review source/reason. Explicit
policy denials cannot be overridden. Update POLICY_VERSION and the publication format when rules change.


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
abi_hash. Public archive names have no ABI suffix. The native publisher writes one release record per batch into the release catalog:
`index.json` lists version/year shards, `releases/<version>.json` stores stable
release history and `master/<year>.json` stores snapshots. No duplicate variant
files or audit data are stored. The original asset date is recorded only when
a ZIP is reused in a newer release. CI looks up ABI in a lazily loaded in-memory
map per version (or master history). Legacy records without current native ABI
and format remain discoverable but are not reused.

`ffbuild publish` verifies the plan and archive digests, creates or uploads
assets to GitHub Release, then writes the release catalog JSON into
the local `data` checkout and commits/pushes that branch. `--dry-run` only
validates local assets; it does not upload or update the database. Nonfree
artifacts are prohibited from publication. Existing GitHub Release assets are
not uploaded with `--clobber`.

## Legacy data and versioning

Historical release entries without native ABI metadata are preserved for access. They do not claim
to contain a native ABI and are not used for ABI deduplication. New native
records are additive. Version indexes retain old entries and count only
native-ABI records toward native build completion.

The native NuGet ABI export is **experimental** in vcpkg. It was tested
against the pinned 2026.06.01 registry/tool on Windows: repeat scans are
stable; changing a selected Feature changes the target ABI; changing a
dependency recipe changes both the dependency ABI and the dependent ABI;
restoring the recipe restores the original hashes. A real minimal package
installation reported exactly the ABI calculated beforehand.

Historical archive formats are still readable but cannot satisfy current
native ABI reuse. All current release artifacts must pass the current
package, compliance and publication gates.

### Supplemental license declarations

The root `licenses/` directory contains one standard SPDX 2.3 JSON document
per Port with missing metadata. The package `versionInfo` follows vcpkg
(version plus #port-version if nonzero), `licenseConcluded` records our
conclusion, `licenseDeclared` remains NOASSERTION, and `sourceInfo` and
`licenseComments` retain the evidence source and scope. Nonstandard terms
carry their actual text in `hasExtractedLicensingInfos`. Unresolved
terms remain NOASSERTION and block packaging. Original SPDX/copyright files
remain in the internal CI audit archive; the public ZIP contains the merged
copyright and generated SPDX SBOM. The applied declaration is recorded in
build provenance. Native known/conflicting/partially unknown expressions are not
overwritten. Existing exact-copyright pkgconf approval remains scoped.
No third-party Port or vcpkg ABI changes are needed.

A correction to a known native expression is allowed only when the local SPDX package's licenseDeclared matches the same SPDX syntax tree (ignoring AND/OR ordering), the Port version matches, and the installed copyright SHA256 matches the SPDX file checksum. The original SPDX is preserved; the normal compatibility gate still applies. glslang is the initial correction.

The reviewed Windows opengl SDK import-only Port is classified as an external system dependency only when its native SPDX has the exact reviewed recipe checksum, matching SDK notice and import-only installed payload. Its license remains NOASSERTION; SDK headers, import libraries and DLLs themselves are prohibited in release archives. Unknown system packages are not exempted.

## Release presentation

Dated Release titles include the UTC date and optional R sequence. Master is
explicitly identified in its title. The English notes describe the actual package
types, architectures, licenses, upstream source and CI run; individual asset
names and hashes remain in GitHub asset metadata and the Data catalog.


### Operational recovery

- Master retention deletes only expired public prerelease assets/Release entries,
  never Git tags. The catalog is modified only after remote deletion is confirmed;
  a failed deletion aborts the Data commit. Missing Releases are checked using
  authenticated listing, not inferred from a failed delete command.
- A publication tag includes the verified canonical batch record and its SHA256.
  The Recover Release index workflow verifies an existing public Release and
  restores its exact index row without rebuilding or uploading anything.
  Tags lacking recovery metadata and deleted/draft Releases are rejected.
- A partial GitHub job rerun consumes the same successful plan generation.
  Successful workers may contribute archives from earlier attempts of that
  generation; later failed workers or a new plan invalidate those artifacts.
  Every downloaded archive still passes the normal publisher checks.
- Same-day R2 through R99 are compared numerically throughout the catalog,
  reuse selection, and snapshot retention.
