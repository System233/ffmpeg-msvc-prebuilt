# CMake black-box contract baseline

This is the pre-fix RED baseline. The tests added here are intentionally
ordinary failing assertions, not expected failures or disabled tests.
Do not change production CMake merely to satisfy a source-text pattern.
Do not weaken the tests to conceal a reproduced defect.

## Scope and test oracles

| Layer | Test suite | Oracle |
| --- | --- | --- |
| Consumer and metadata | test_cmake_blackbox.py | Actual CMake configure/generate, selected import library and DLL paths, evaluated dependencies and legacy link items, diagnostics |
| SDK boundaries | test_cmake_sdk_contract.py | Historical/minimal packages, version rejection, component propagation, target width, search isolation, exact filenames and dependency-path precedence |
| Native compiler/linker and extracted SDK | test_cmake_blackbox_msvc.py | Real MSVC archives and DLLs, CRT mismatch, executable results, actual loaded DLL paths, installed DLL bytes, real vcpkg wrapper, real PDB pairing, Native Tester link commands |
| Full Port control flow | test_cmake_port_contract.py | Complete generated Port, real pkgconf and pinned vcpkg helpers, actual generated shell with configure/make/install, native lib.exe DEF conversion, install layout and evidence |
| Existing real FFmpeg integration | test_cmake_real_sdk.py | Current CMake metadata on a scratch copy of a real shared package, authored Native Tester, pkgconfig consumer, production ZIP packer and extracted SDK acceptance |

The lightweight consumer fixtures use placeholder files but the actual metadata
producer and CMake generator. The Port fixture executes the whole generated
Port, not a source slice; source acquisition, compiler detection, the expensive
FFmpeg build, and selected installation helpers remain boundary test doubles.
Selected cases execute the actual generated production build.sh with real Bash,
a small configure fixture, and real GNU make. They also exercise the real
vcpkg pkgconfig fixup and search helpers and actual lib.exe on generated DEFs.
These tests do not claim to build upstream FFmpeg or run its actual configure
script. Native compiler fixtures produce real C/C++ binaries and PDBs.

The real-package tier reuses previously built FFmpeg binaries and regenerates
current metadata in scratch storage; no upstream source rebuild or official
publication is claimed. It deliberately omits large existing PDBs from that
runtime repack, since real-native symbol pairing has its own test. The actual
release Worker matrix and full production publication gate remain necessary.

## Reproduce

Use the strict runner from the repository root. Missing mandatory prerequisites,
unexpected skips and expected failures are not silently accepted.

```powershell
$env:FFBUILD_TEST_PKGCONF = "<host pkgconf executable>"
python tests/run_cmake_contracts.py --tier quick

$env:FFBUILD_TEST_VCPKG_ROOT = "<pinned vcpkg checkout>"
$env:FFBUILD_TEST_LIB_EXE = "<VS 2022 host lib.exe>"
# Optional if the pinned vcpkg MSYS2 bash/make is not auto-discovered:
# $env:FFBUILD_TEST_BASH = "<MSYS2 bash.exe>"
python tests/run_cmake_contracts.py --tier native

$env:FFBUILD_TEST_REAL_PACKAGE = "<previously built shared FFmpeg package>"
$env:FFBUILD_TEST_REAL_INSTALLED = "<matching installed triplet prefix>"
# Default x64-windows; x86-windows is also supported.
python tests/run_cmake_contracts.py --tier real --report _work/cmake-contract-result.json
```

The quick tier covers portable discovery and metadata contracts and existing
recipe/archive guardrails. Native includes quick plus MSVC and full Port
contracts. Real includes native plus existing actual FFmpeg package acceptance.
The runner sets the native opt-in flag and Python import path itself; the
normal unittest discovery entry remains available for individual tests.
For bounded local runs, select modules (repeatable) or a specific test ID
pattern. The default tier still includes all its modules. Do not interpret
a filtered report as a complete tier result.

    python tests/run_cmake_contracts.py --tier quick --module test_cmake_consumer
    python tests/run_cmake_contracts.py --tier native --module test_cmake_port_contract
    python tests/run_cmake_contracts.py --tier native --module test_cmake_blackbox_msvc --match "*shared_binary_overlay*"

The runner executes independent test methods concurrently in isolated Python
worker processes by default (up to eight workers). Tests with shared class
or module fixtures stay together. The real SDK methods now each use a small
isolated scratch copy (excluding PDBs), so their independent compile/run and
archive acceptance checks also execute concurrently. Longer native/real
work is submitted ahead of short Port probes.
Native/Port work has a separate concurrency cap of two workers by default;
this avoids oversubscribing MSBuild and compiler subprocesses. Both limits
are configurable, and serial execution remains available for diagnosis:

    python tests/run_cmake_contracts.py --tier native --jobs 8 --native-jobs 2
    python tests/run_cmake_contracts.py --tier quick --jobs 1

The report records the selected modules/filter, per-test timings, measured
peak concurrency, worker failures and any methods not executed. Worker
failure, missing tests and unexpected skips fail the gate. Test
commands close stdin, disable MSBuild node reuse and use bounded waits
(60 seconds for ordinary commands, 120 seconds for builds). On timeout,
the bounded subprocess helper terminates the command tree and records an
error; file-backed output avoids waiting for inherited pipe handles. Every
fixture group runs in a fresh interpreter supervised by a hard deadline
(default 300 seconds, --group-timeout). A hung worker is reported as
unsuccessful evidence, independently of the remaining groups. The external
task timeout is separate: run heavy modules or individual cases separately
if a complete tier exceeds it.

The historical RED runs returned nonzero for the failures below. The strict
runner still rejects missing tests, failed assertions and unexpected skips.
No CI workflow changes are included.

## Executed baseline (Windows x64)

| Suite | Test methods | Passed | Failed methods | Failed assertions including subtests |
| --- | ---: | ---: | ---: | ---: |
| Consumer and metadata | 23 | 11 | 12 | 16 |
| SDK boundaries | 20 | 16 | 4 | 4 |
| Full Port control flow | 25 | 15 | 10 | 10 |
| Native compiler/linker and extracted SDK | 7 | 5 | 2 | 2 |
| Existing real FFmpeg integration | 3 | 3 | 0 | 0 |
| New tests total | 78 | 50 | 28 | 32 |

All 78 new test methods were executed, including targeted reruns after
correcting test-fixture issues, with no skips. The first RED baseline contained
37 new methods; 41 additional methods extend that baseline. All 55 existing
CMake, metadata, MSVC, shared pkgconfig, Debug Add-on, recipe and archive
regression tests passed. The strict quick runner itself executed 97 methods: 81 passed, 16 failed (20 assertions), zero errors and zero skips; it returned nonzero and emitted a structured JSON report. It also rejects a missing pkgconf prerequisite.

Additional executed coverage:

- Ten latest source-backed version families and one pinned Master fixture
  execute the full generated Port control-flow and Config consumer. These are
  fixture builds, not full upstream builds of eleven versions.
- Four architecture mappings and 24 real DEF-derived COFF import archives
  (three modules, Release/Debug, x86/x64/ARM/ARM64) passed machine checks.
- Generated build.sh ran real configure fixture, GNU make and install in both
  configurations. Injected failure at configure, make and install was propagated.
- Real vcpkg fixup preserved static private dependencies, cleared shared private
  links while preserving the graph, and produced relocatable pkgconfig paths.
- Real MSVC CRT pairs and wrong-CRT mutations, loaded DLL path and identity,
  wrong-DLL runtime control, and real vcpkg PDB copy/identity passed. The
  required-link-option positive control passed; SDK-only execution returned 11.
- Actual existing FFmpeg 8.1.3 x64 shared package: 39 Release and 39 Debug
  Native Tester programs compiled and executed, 12 extracted ZIP consumer
  executions passed, 3 CLI version checks passed, and both real pkgconfig
  consumer configurations compiled and ran. No new FFmpeg source build.

## CRT contract and test boundaries

The four supported Windows triplets (`x86`, `x64`, `arm`, `arm64`) select
`VCPKG_CRT_LINKAGE=static` and `VCPKG_LIBRARY_LINKAGE=static`. For these
triplets the FFmpeg Port and its vcpkg dependencies use `/MT` in Release and
`/MTd` in Debug. The Port's `/MD` branch remains covered only as generic
compatibility with an explicitly dynamic-CRT vcpkg triplet; it is not the
consumer CRT selection and is not used by the project's supported triplets.

The public Windows SDK is shared. Its FFmpeg DLLs own their static CRT; their
import libraries do not impose that CRT on the application. Shared SDK
consumer tests therefore exercise `/MT`, `/MD`, `/MTd`, and `/MDd` against
both a Release-only package (including Debug-to-Release fallback) and a
complete Release+Debug overlay. They also assert that FindFFmpeg does not
rewrite `CMAKE_MSVC_RUNTIME_LIBRARY`, verify the target's evaluated runtime
selection, check the actual compiler CRT macros, and inspect DLL imports for
dynamic MSVC/UCRT dependencies. The real-package tier compiles a small C/C++ consumer matrix against an existing
FFmpeg build and checks its actual DLL imports, independently of the full
Native Tester sweep.

Static archive tests have a different scope: they verify that FFmpeg and its
internal static dependency graph are built with the CRT selected by the
vcpkg triplet, and reject a Release archive mislabeled as a Debug dependency.
The public distribution does not provide the multi-gigabyte static SDK, so
these tests do not establish a public cross-CRT static-linking guarantee and
must not be used to restrict consumers of the shared SDK. C-only static
archives can sometimes link across CRT choices with linker warnings, while
C++ objects may carry `RuntimeLibrary` and STL iterator mismatch directives;
that distinction is not a reason to couple a shared DLL consumer to its
internal CRT.

## Shared versus locally built static dependency closure

Do not conflate the distribution policy (no static SDK ZIP) with support for
a native vcpkg static install. The shared SDK must not require third-party
static archives, their private pkg-config packages, or their private Cflags
after the dependencies have been linked into its DLLs. The internal FFmpeg
module graph, version constraints, and genuinely public requirements and
flags must remain intact. The static Port instead retains its complete
link closure, including external packages reached through Requires.private
and Libs.private. The real vcpkg fixup folds private fields into the public
fields for static packages, so an ordinary pkgconf --libs is sufficient.

Additional contracts execute the complete generated Port and actual pinned
vcpkg fixup, then relocate the installation and isolate the pkgconf search
path. The native fixture creates real MSVC static archives and DLLs with
a multilevel dependency graph (avformat -> avcodec -> avutil -> third ->
leaf), plus a second private archive and a Windows system library.
The local static consumer merges the Port with its dependency packages,
removes the original producer build and relocates the prefix. Release and
Debug use /MT and /MTd respectively. All four CMake interfaces and a real
PkgConfig imported target link and execute; removing the transitive Debug
leaf must fail discovery. The shared consumer deletes all private packages
and the producer build before configuring, linking and executing the four
CMake interfaces and attempting the same PkgConfig consumer.

The complete parallel baseline before this extension ran 145/145 methods:
117 passed, 28 failed (32 failure assertions), no errors or skips, in
267.86 seconds with measured peak concurrency 12 (native 4).
The dependency-focused extension ran ten distinct methods (including
targeted reruns): seven passed and three failed. Static dependency metadata,
native CMake/PkgConfig links and the missing-leaf negative control passed.
All three failures expose the surviving external Requires.private entry
in shared metadata, including the raw mixed public/private requirement
case. Normal and --static pkgconf queries fail after the private package
is removed. The original shared native CMake consumer still links/runs.
No production changes were made for this extension.

A first static native pkg-config test also reproduced a separate path
parsing failure in CMake FindPkgConfig when the relocated prefix contains
spaces. To isolate the dependency-closure contract, the native pkg-config
fixture uses a relocated prefix without spaces; the Port's CLI relocation
test retains spaces. This does not establish support for space-containing
prefixes through CMake FindPkgConfig.

For actual FFmpeg static installation acceptance, the separate real-static
tier requires both the genuine built Port package and its corresponding
installed triplet, rather than copying multi-gigabyte archives:

    $env:FFBUILD_TEST_REAL_STATIC_PACKAGE = "<actual static Port package>"
    $env:FFBUILD_TEST_REAL_STATIC_INSTALLED = "<matching installed triplet>"
    python tests/run_cmake_contracts.py --tier real-static --module test_cmake_real_static_sdk

Set FFBUILD_TEST_REAL_STATIC_TRIPLET=x86-windows for native Win32 execution
(default x64-windows). This tier checks static CRT/package identity, real
Native Tester target links for both configurations and the actual
PkgConfig consumer exercising codec/format/filter registration. It is
intended for a complete core-module build; it fails on missing inputs
rather than treating them as a successful skip. These two tests have not
been run against a real static FFmpeg build locally: the available FFmpeg
8.1.3 package is shared. The missing-input guard was exercised successfully.

## Failures reproduced before repairs

| Contract | Observation |
| --- | --- |
| Shared SDK selection diagnostics | No mapping output, including ordinary Release-only fallback |
| Partial Debug add-on | Whole SDK falls back correctly but no warning |
| Custom DEBUG_CONFIGURATIONS | ASan can select Release module and Debug dependencies |
| Custom imported configuration map | Target selects Debug while legacy selects Release |
| SDK identity | A 4.4.8 Module can report that version while linking another SDK |
| Component status | Missing Debug dependency leaves component FOUND true |
| Explicit opposite-config search path | Accepted and silently reinterpreted by metadata producer |
| Explicit manual-link path | Directory is discarded |
| External absolute library | Machine-specific path is accepted in generated metadata |
| Unknown vendor library | Unknown absent name passes producer as if it were a system library |
| Native Tester | With an incomplete shared Debug SDK, generated Debug link command selects Release |
| Required link option | Real registration object omitted; positive control with explicit /INCLUDE works, SDK-only execution fails |
| Native Configure pkgconf environment | External Release .pc can satisfy a missing Debug .pc via either PKG_CONFIG_PATH or PKG_CONFIG_LIBDIR |
| License evidence | Different Debug license, missing Debug license, or unrequested GPL in both configurations accepted |
| Feature evidence | Requested Tesseract absent in Release or Debug config.h accepted |
| Native artifact completeness | Port accepts missing Debug DLL or static archive |
| Legal absolute dependency path | Matching installed archive path survives metadata generation as a stale absolute reference after relocation |
| Explicit search precedence | Same-name archive in explicit manual-link directory loses to default lib directory |
| Transitive component status | Missing Debug dependency leaves dependent components FOUND |
| Failed initial exact request | Wrong version is rejected but linkable imported targets remain |
| Single-config triplet | Release build runs before unsupported package layout is rejected |

Unknown vendor rejection is a proposed strict producer contract, not proof
that any particular real Windows system library is invalid. A future
implementation must distinguish actual toolchain libraries using evidence,
not an arbitrary whitelist. The single-config case intentionally constrains
the current project's dual-build Port; it is not a claim that vcpkg itself
does not support single-config triplets. Failure diagnostics are tested for
meaning rather than exact punctuation.

## Preserved behavior

Release-only shared SDK works in Debug without a requirement for Debug CRT.
An incomplete overlay must not mix FFmpeg modules. Complete SDKs select
Debug in standard Debug configurations. All other standard configurations
select Release. FFmpeg DLLs and their bundled static dependencies use the
triplet-selected CRT; the current supported triplets select `/MT` and `/MTd`.
Consumers of the shared SDK may independently use `/MT`, `/MD`, `/MTd`, or
`/MDd`; FindFFmpeg must not rewrite their CRT. Native static-archive fixtures
validate producer-side CRT consistency and local-install dependency closure. Native fixtures run aggregate,
demand, legacy and alias linking, test actual DLL deployment and install, and
distinguish different binaries even when they have the same name. No new
public configuration option is required.

Before the next production edit, use these tests as the baseline. After
each repair, run all old and new groups, not only the test being fixed.
The final green gate still requires actual FFmpeg and native vcpkg CI
coverage (including 4.4.8) and real release-archive verification.

## Repair verification (2026-11-28)

The original RED baseline plus the five executable shared/static dependency
extension methods was verified GREEN by three non-overlapping parallel runs:
108 quick methods, 9 native MSVC SDK methods, and 33 remaining native/real
methods (150/150, no errors or skips). The last group included all 28 Port
methods and four real FFmpeg 8.1.3 SDK methods. Existing binaries were reused
and metadata was regenerated; this was not a new upstream FFmpeg build.

Additional audit found that the original MSVC global explicit /LIBPATH for
the default installed directory could override an explicit manual-link
directory emitted by pkg-config. A real native link experiment with two
archives of the same name returned 11 for default-first, 22 for manual-first,
22 for explicit manual directory with default in LIB, and 11 for LIB-only.
The MSYS-to-MSVC experiment also returned 22 and 11 respectively. The Port
therefore retains the configuration-specific default directory as a LIB
fallback, restoring the caller's environment. Non-MSVC keeps its existing
-L flag. This makes explicit pkg-config search order and installed SDK
metadata resolution agree rather than silently selecting a different archive.

The feature check now splits every explicit feature's enable switches and
requires actual generated configuration evidence, not a successful build
exit alone. Core modules are validated by their installed module artifacts,
license switches by the actual license output. A survey of 138 locally
available upstream configure scripts confirmed the CONFIG_* convention;
thread switches use HAVE_* and historical SDL2 can use HAVE_SDL2 when
CONFIG_SDL2 does not exist. The extra seven Port tests (four reproduced
failures and three supporting controls) cover the LIB fallback and restore,
OpenSSL, multi-switch NVENC, SDL2 compatibility and nonfree licensing.
The follow-up parallel run passed 38/38 methods (35 Port and three recipe
parity tests). This replaces overlapping earlier results, yielding 157
distinct executed methods passed; two real static FFmpeg acceptance methods
still require an actual static installation. The Windows-only fallback
experiment was real MSVC; the Port feature/architecture tests use controlled
external-build fixtures. No patch bytes, feature presets, release ZIP policy
or supported triplet CRT strategy were changed.

The remaining acceptance requirement is native source-build CI (including
FFmpeg 4.4.8 with its actual Tesseract/ZeroMQ dependencies, shared and static)
and the actual static SDK tier. At this repair stage the pkg-config path-with-spaces issue was still
outside the dependency closure correction (see follow-up below). Do not interpret the
local fixture/previously-built shared binary evidence as proof of a new
full source matrix or a new public release.

## Follow-up closure: paths, licensing, bounded validation

Native pkgconf 2.5.1 expands variables containing spaces with escapes.
The pinned vcpkg fixup surrounds variable-only -L/-I flags with quotes,
which causes pkgconf to emit a second escape and breaks both metadata
search-order resolution and CMake FindPkgConfig. A four-form direct
pkgconf experiment isolated the quoted flag as the cause. FFmpeg's own
normalized Windows .pc files now unwrap only variable-only path flags,
preserving literal flags and all static dependency fields. The production
metadata parser also decodes the extra escape in output from existing
third-party .pc files, retaining explicitly selected manual-link archives.
No third-party package is modified.

The restored native tests relocate both shared and local static SDKs
to space-containing paths and run the CMake and PkgConfig consumers.
Both passed (2/2). The shared SDK also drops Cflags.private; public Cflags
and public requirements remain intact. The Port's explicit version3
request now rejects version2 evidence for both LGPL and GPL, with nonfree
handled separately. Three additional defect-focused tests reproduced the
original incorrect behavior and passed after correction.

The subprocess helper is shared by the contract fixtures and production
archive acceptance. Archive extraction now deliberately uses a directory
containing spaces and verifies actual --cflags/--libs tokenization, as well
as the existing module, version, runtime and configuration checks.
Each contract group is supervised by an independent process deadline;
a deliberate hung-worker probe confirms that another worker can succeed
and that the aggregate is still a failure, with no invented result.
The quick suite and autoheal-native regression are separately verified.
Direct PkgConfig use of third-party static dependencies still depends on
those packages' own metadata; no global pkgconf wrapper or dependency
metadata rewrite is introduced.

An isolated real static FFmpeg 8.1.3 x64 vcpkg plan was prepared without
changing the existing shared installation. A cache-only preflight for
the required dependencies restored zero matching packages and failed
before any dependency/source compilation. A full static source build and
the real-static acceptance tier therefore still require the CI dependency
cache or an explicitly provisioned local environment. This is a validation
prerequisite, not a successful source-build result.

Final closure verification: the full quick run passed 112/112 in 107.062s
(peak concurrency 8). The native/real run completed 50/50 methods in
250.078s (peak concurrency 4), with one archive-validator error: pkgconf
also escapes spaces in --variable output. The validator now accepts only
an exact path after decoding one shell token (or an exact raw path). An
additional regression checks both SDK configurations and rejects a wrong
directory. The affected 24-method regression passed 24/24, and the real
FFmpeg 8.1.3 archive acceptance rerun passed 1/1 in 27.984s. Deduplicated
latest results: 163/163 methods passed. Nine autoheal-native tests and the
26 source-backed Port / 3 YAML template configuration check also passed.
Two actual static-source acceptance methods remain unexecuted; the cache
preflight failed before compilation, and no remote CI was dispatched.

## Native Windows CI policy initialization

CI is restricted to Windows for the CMake/MSVC contracts; the metadata-only
fixtures use the host's native Windows platform semantics, not a forced
cross-compilation configuration. The previous Linux-oriented repeated
escape loop was reverted after a native timeout. The Windows native tier
passed 159/159 (no skips) after the correction.

The Windows runner then reported two independent licensing-probe failures:
both generated script-mode entrypoints lacked a CMake policy baseline.
Local CMake 4.3.3 already reports CMP0057 NEW in uninitialized script mode,
whereas the runner reported it unset and rejected IN_LIST. The pinned vcpkg
scripts/ports.cmake explicitly establishes CMake 3.21. Both probes now
declare that same baseline, verify a success marker after executing the
actual generated guard, and require the exact license diagnostic on
rejection. The shared pkg-config script-mode probe also uses 3.21.
The remaining script-mode test entrypoints were audited and already
declare 3.21. The production builder and license rules are unchanged.
All three affected test modules passed locally (33/33).

### Windows filesystem path identity

The next Windows CI run executed all 159 native-tier methods (135 passed,
24 failed, 36 failure assertions, no skips). Its temporary directory used
Windows 8.3 names while CMake returned expanded real paths. Two-sided
filesystem normalization was missing from the legacy-link containment
assertions and three imported-location assertions. Local GetShortPathNameW
reproduction failed all five selected methods (six failure assertions)
before correction and passed all five afterward.

Existing absolute paths are now resolved strictly on both sides of each
comparison. Imported-location evidence is written by the actual CMake
consumer, compared against independent fixture inputs, and removed before
reconfiguration to prevent stale evidence. Additional tests exercise a
real 8.3 alias when available (a distinct parent-component path spelling
on volumes without short-name aliases), and reject wrong-config, foreign
SDK, missing and relative library paths. The production CMake builder,
SDK templates, licensing rules and dependency cache keys are unchanged.
All 73 methods across the three affected modules passed in an actual
8.3 TEMP/TMP environment, with no skips.

## Unified external SDK Tester (consumer-only)

The authored vcpkg Port remains `ffmpeg-tester`. It compiles C and C++
against a single Config-only discovery in each native Release/Debug build;
a missing Debug artifact is fatal. The seven core libraries plus historical
modules independently required by the build plan are mandatory. Additional
upstream FFmpeg modules found in the installed pkg-config inventory must
also have a probe. Vendor .pc files are not FFmpeg modules.

`ports/ffmpeg-tester/CMakeLists.txt` is also the sole real SDK consumer
project. It exposes independent CONFIG, MODULE, LEGACY and PKGCONFIG
entry points. Each mode has its own configure/build tree; Config receives
only CMAKE_PREFIX_PATH as a discovery hint, Module/Legacy locate the
selected Find module, and PkgConfig uses an explicit native pkgconf and
isolated per-stage, per-configuration .pc directories. The metadata-only
contract fixtures remain independent test oracles.

Stable public version functions, allocation/release and registry symbol
references exercise headers, exported symbols and linker dependency
closure. No codec, media, device, network, or GPU functionality is
required. Legacy registration calls are selected by library version
macros. C++ compiles all public module headers while the lightweight
full-target probe calls avutil; one comprehensive C program references
all modules. Native Port targets are per-module demand links plus those
two full-target probes (nine for seven libraries). Optional historical
modules add one demand case each.

Public shared SDK acceptance covers Binary-only, complete Debug overlay
and removal using separate Config/Module/Legacy/PkgConfig projects.
The overlay executes per-module demand links and the two full probes;
Config also exercises C and C++ /MT, /MD, /MTd, /MDd in their normal
Release/Debug configurations. The Binary-only Debug consumers must load
Release DLLs, while full native builds may never silently fall back.
Consumer builds do not unpack PDBs (publication verifies PDB identities).
Selected imported files and pkg-config library paths are checked against
real configuration-specific SDK paths; runtime deployment is isolated.
The static installation is tested outside the vcpkg toolchain using all
four modes with /MT and /MTd. Static releases remain CLI-only.

Worker reports are separate from published assets. Autoheal reconstructs
the exact native Tester case IDs from the selected module set and
independently checks requested historical modules against the pinned
feature plan, rather than accepting fixed target counts. Old repair
evidence without case identities must be regenerated. ARM/ARM64 retain
native toolchain compile/link coverage; this Windows x64/x86 public
runtime gate does not claim ARM execution. Test-only source changes are
excluded from dependency Seed cache keys; real native ABI coverage is
still mandatory.

Production SDK commands:

```
python -m ffbuild.ci verify-installed-sdk --job-env FFBUILD_JOB --installed-root <installed> --pkgconf <pkgconf.exe> --report installed-sdk-tests.json
python -m ffbuild.ci verify-sdk --artifacts-dir Release --pkgconf <pkgconf.exe> --report public-sdk-tests.json
```

Local implementation validation: real Windows x64 shared SDK archives for 4.4.8 LGPL and 8.1.3 GPL each passed 99 distinct CLI/consumer cases (24 Binary-only, 66 overlay, 6 overlay-removed, 3 CLI). Quick contracts passed 117/117 with no skips; the two targeted native Tester contracts passed. Full source-built static SDK validation and historical optional-module coverage remain CI acceptance requirements.
