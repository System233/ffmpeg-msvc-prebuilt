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
`ffmpeg-9-1`, etc.) with no generated dependency aggregator Port. As of November
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
  resolved recipe, inheritance and patch bytes. They validate all configured
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
- The native ABI plan is one immutable artifact for a single production
  version. The expected target set is generated from the declared matrix
  dimensions and validated by identity, not a fixed number. Only missing
  native ABIs are built on a production request; authorized Bot PRs force
  verification of the complete target matrix. CI rejects duplicate targets,
  multiple versions and matrices beyond GitHub Actions' 256-job limit.
  Local JSON planning remains unrestricted.
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
authorized Bot PRs: dry_run, force, skip_publish and skip_release. Explicit
manual dispatches on main can also select dry_run with target_arch and/or
target_license; these runs never publish and do not narrow the production
or Bot PR matrix. Ordinary
branch pushes cannot use this entrypoint to run native builds. The temporary
branch-driven E2E workflow is not part of the production tree. Any additional
remote smoke harness belongs on an isolated, separately reviewed test branch.

## Shared dependency prebuild and CI caches

The original CI optimization is retained: third-party dependency libraries
are **statically linked** and prebuilt once per Triplet before independent
FFmpeg Workers start. Dependency DLLs are **not** collected or packaged as
Release artifacts; only FFmpeg Port outputs are packaged. Versioned FFmpeg
Ports do not imply version-specific copies of identical dependencies.

The dependency Seed is an archive set, not a vcpkg Port. Plan scans every
source-backed release and the pinned Master recipe against the declared CI
target matrix using vcpkg's native install plan. Identical dependency
declarations are scanned once, including linkage-only variants whose
requested Features have no dependency edges. Each native plan records the
complete package specs (including explicit core, Features and host Triplet)
and ABI hashes, excluding only the two FFmpeg target packages. The Seed selects a deterministic cover of the original observed graphs.
It never combines unrelated graphs into a synthetic install batch: different
Ports may own the same installed files even when a dry-run reports unchanged
ABIs. vcpkg must independently reproduce each selected exact ABI and spec
graph without an FFmpeg overlay.
No packages outside the declared CI matrix are intentionally prebuilt.

CI's work order is:

1. `plan` generates all versioned Ports including a pinned Master. It scans
   only the **one selected release version** for publication scheduling, but
   derives the shared dependency plan for all versions and all configured Triplets
   when there is work. Actual selected target graphs must be covered by that
   dependency plan. It outputs only the Triplets with unpublished native ABI work. The ARM SDK
   selection workaround is applied **before** the ABI scan, matching Prepare
   and Build runners so the planned compiler ABI does not depend on a different
   SDK selection.
2. `download` restores a shared vcpkg downloads cache, or runs `ffbuild.ci download` across all configured Triplets and
   saves the consolidated downloads. Previously published download caches are
   used as fallback sources. Download-only execution resolves package specs,
   not binary ABI equality across runners.
3. `prepare` runs once per **needed Triplet**, restoring a prior binary Seed
   when possible. The native preparation command verifies each batch ABI against Plan before installation.
   A new ABI set restores the previous cache for that Triplet and lets native
   vcpkg reuse matching archives and populate only missing packages. If the
   current identity cannot be restored, preparation retries in readwrite mode
   against the same directory. Before publishing a new cache, it restores each
   batch in cache-only mode and checks installed ABIs. A failed refresh is fatal.
   After verification,
   unneeded vcpkg ABI archives from earlier current-namespace plans are removed only from
   the dedicated CI cache; local and shared repair caches are not pruned.
4. Each `build` Worker restores the shared source downloads and the **exact
   same completed Seed ABI identity, read-only from GitHub Actions**. A missing cache fails the job instead of silently
   rebuilding all dependencies independently. The worker vcpkg binary source
   itself is `read` rather than `readwrite`, preventing redundant FFmpeg ZIP
   writes on a space-constrained Windows Runner. **Before building, the Worker
   queries vcpkg's native ABI graph including the FFmpeg Consumer Tester and
   requires a nonempty files-provider ZIP for every third-party ABI**; missing
   dependency packages are fatal rather than locally compiled. Before the target
   install, the Worker restores exact native external feature specifications
   using `--only-binarycaching`, compares installed ABIs and verifies the
   remaining native plan contains only FFmpeg and Tester. The target install
   does not allow recursive replacement. **After building, the Worker checks
   buildtree logs** as defense in depth. Only FFmpeg and Tester may build.

The binary cache namespace is scoped by pinned vcpkg version, Triplet and
SHA256 of the newline-joined, lexically sorted **unique external native ABIs**.
It excludes FFmpeg, Tester, dependency grouping labels and any virtual Port.
GitHub cache entries cannot be overwritten. If an existing cache for the exact
ABI identity cannot be restored but native population succeeds, Prepare saves
a replacement under the same ABI key with a run/attempt suffix. Restore prefers
that generation before the canonical key. Healthy cache hits never create a
new generation; Workers cannot fall back to a different ABI identity.
The dependency plan retains package names and specs for diagnostics and
execution, not as additional cache-key inputs. Source download cache identity
uses the union of native external specs and dependency recipe files, not
compiler/tool ABI hashes. Only the current `ffbuild-seed` namespace may supply existing binaries;
only `prepare` writes the consolidated GitHub binary cache. There is no independent environment fingerprint.

Seed builds use `--clean-buildtrees-after-build` and
`--clean-packages-after-build`, **not** `--clean-after-build`: the latter also
deletes the downloads cache. All these commands run on Windows CI, never as
part of local Python tests or `generate --all`.

## Scan native ABIs without compiling

The version-controlled environment in `.github/ci.env` is the single
declaration of `VCPKG_TAG`, `TRIPLETS`, `LICENSES`, `LINKAGES`,
`VCPKG_INSTALL_OPTIONS`, and `ARM_WINDOWS_SDK`. It uses literal
KEY=VALUE lines (no shell expansion). All workflows and local tooling read
the same declarations; explicit environment variables may narrow local
tests. The matrix is the Cartesian product of the declared axes.
`setup-vcpkg` initializes the Python and vcpkg environment once per native
Runner. The CI Plan command generates the complete immutable release plan,
native Seed plans, and cache identities. The Download and Prepare jobs
consume that plan. Exact Worker restores use the official GitHub cache
Action directly. Download, Prepare and Auto-Heal also use the official
cache restore Action, with incremental reuse restricted to their current
cache namespace and matching vcpkg version.
Auto-Heal restores only the incident Triplets with the same cache action;
four positional restore slots cover the supported Windows architectures.
Native ABI validation and final cache-only verification still fail closed.
Dependency submission uses one Windows Runner, one source snapshot and
one generated Port set across all configured Triplets.
Local Python bootstrap requires VCPKG_TAG or an explicit tag if vcpkg is
not installed. All native install modes consume VCPKG_INSTALL_OPTIONS
and reject configuration that omits VCPKG_FORCE_DOWNLOADED_BINARIES=1 or the mandatory
--x-abi-tools-use-exact-versions guard.
The setup action also preserves PYTHONIOENCODING=utf-8. Its `install --dry-run` command supports
the experimental `--x-write-nuget-packages-config=<path>` option. The resulting
NuGet `packages.config` gives each Port's full native ABI in its
`<version>-vcpkg<sha256>` package version.

```powershell
python -m ffbuild scan --version 8.1.3 --output ffbuild-abi.json --abi-evidence abi-evidence
python -m ffbuild plan --abi-file ffbuild-abi.json --state-dir data
```

Use `scan --history` for every source-backed stable release; the default
without `--version` selects the latest release in each family, while the
generator still prepares *all* versions. The shared environment declarations select
other native Package Specs/Triplets. The matrix generator produces native package profiles
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
Plan, Prepare, Worker and Auto-heal retain native ABI input files and graph.json
as diagnostic artifacts. Each input file must match its native SHA256.
Compare corresponding graph directories with
python -m ffbuild.ci compare-abi BEFORE AFTER to identify per-package and
per-component changes (including tools and transitive dependency ABIs).

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
for its target and Tester; it fails if either the target ABI or the complete
native dependency graph differs from Plan.

The centrally prebuilt native vcpkg binary cache remains active for dependency reuse; `data`
tracks **published artifacts**, not whether a package is present in cache.

## Package, data and publish

The CI executes `ffbuild.ci worker-package` (the same native packager and dry-run publication gate)
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

Public SPDX source information includes the pinned FFmpeg upstream identity and
checksum, CI recipe commit when available, and public dependency resource URLs
and checksums from native vcpkg SPDX. These durable pointers improve source
traceability without adding new ZIP members. They are not a corresponding
source delivery mechanism or certification of LGPL relinking obligations.

## CMake regression tests

The shared Port still uses FFmpeg's normalized vcpkg pkg-config metadata,
per-module dependency graph and topological cleanup. The installed Find module
contains only relocatable module metadata. Native MSVC package dependencies
are pinned to the matching configuration directory; bare system-library names
remain the linker's responsibility. A public Shared Binary may use the Release
DLLs for Debug, while an installed complete Debug Add-on selects Debug for
every module. A native Static Port cannot fall back between configurations.

The lightweight tests invoke production CMake (no full FFmpeg build).
Use the strict parallel runner rather than serial unittest discovery:

```powershell
$env:PYTHONPATH = "scripts"
python tests/run_cmake_contracts.py --tier quick --jobs 8
```

CMake and Ninja are required for consumer configuration tests; pkgconf is
required for the actual production dependency-pipeline tests. Set
`FFBUILD_TEST_PKGCONF` to a host pkgconf executable if it is not on PATH.
On a Windows host with Visual Studio 2022, opt into a small real MSVC test:

```powershell
# Set the native prerequisites described in cmake-contract-baseline.md.
python tests/run_cmake_contracts.py --tier native --jobs 8 --native-jobs 4
```

It builds real /MT and /MTd archives, links and executes all three consumer
modes in both configurations, checks that a wrong CRT archive produces a
linker error, and checks that a missing Debug dependency cannot silently
resolve from Release. The full FFmpeg Native Tester and ZIP consumer checks
remain separate end-to-end gates. No public Static SDK is introduced.
The local static install retains its full third-party dependency graph.
Shared SDK private link/package/compile flags are removed without changing
public requirements. The paired Port checks actual feature and license
evidence; the explicit version3 switch requires GPLv3/LGPLv3 (or nonfree
when selected). Windows pkgconf variable-path quoting is normalized for
FFmpeg's own .pc files and producer-side library resolution also handles
the quoting in existing dependency .pc files.

The parallel runner has an independent hard deadline for every test group
(default 300 seconds; use --group-timeout for large real builds), and
reports timeout/worker failure as unsuccessful evidence. SDK archive
validation uses a space-containing extraction path and bounded subprocesses.
Third-party packages' own pkg-config files are not rewritten: a direct
PkgConfig consumer of a static install still depends on their metadata
being valid. The generated CMake Config interface does not invoke pkgconf.

New SDKs also support `find_package(FFmpeg CONFIG REQUIRED)` with
`-DCMAKE_PREFIX_PATH=<sdk>`. CMake's generated version file preserves
minimum-version matching and checks target pointer width when known.
The Config and Module entries share the same target implementation;
the Native Tester and extracted SDK consumer exercise both entry points.
Previously released SDKs keep the original Find Module invocation.

See [CMake black-box contract baseline](cmake-contract-baseline.md) for the
pre-fix test matrix, native prerequisites, and deliberately failing contracts.
