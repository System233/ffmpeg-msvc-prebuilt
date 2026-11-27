# Understand the real build chain

Read the current checkout, not the last successful release or a historical patch list.

| Input | Responsibility |
|---|---|
| ffmpeg/*.yaml | Source, inheritance, ordered patches, build options, feature and dependency policy |
| patches/ | Authored upstream source changes |
| ports/ | Local dependency overlays; ffmpeg-tester is the stable consumer |
| triplets/ | Target architecture, CRT, compiler and vcpkg settings |
| vcpkg-configuration.json | Registry baseline and overlays |
| scripts/ffbuild/spec.py, targets.py, port.py | Resolve YAML, compile feature requests, generate native Port |
| scripts/cmake/ffmpeg-portfile.cmake, build.sh.in | Source preparation, configure, make, install, MSVC library/SDK fixups |
| .github/workflows/build-release.yml | Actual generation, scan, dependency preparation, worker, audit and packaging |

The pipeline is YAML -> generated version directory -> native ABI plan -> shared dependency Seed -> native vcpkg install of ffmpeg and ffmpeg-tester -> consumer/build verification -> packaging -> publication. Directory names select source versions; the native manifest always names the package ffmpeg. Never substitute a version-qualified package name or hand-edit generated output. Native ABI is computed by vcpkg.

Read the current workflow step and generated Port before diagnosing. The worker should use prepared dependencies rather than compile third-party packages; failure to prepare or restore them is not evidence of a FFmpeg source bug. The CMake Port downloads/extracts the pinned archive, applies patches in order, sets feature-dependent configure and toolchain options, invokes build.sh for applicable release/debug builds, and installs/normalizes the SDK. The tester consumes installed headers and libraries. A packaging or publishing failure belongs to a different stage.

The Windows repair runtime provides MSVC, pinned vcpkg, verified source and dependency caches. Build selected representative variants through autoheal build/test/smoke; the supervisor repeats clean native validation before delivery. Full matrix CI remains the merge authority.
