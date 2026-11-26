# FFmpeg source configuration

Use the current ffbuild.spec resolver, not a manually reconstructed YAML merge.
The inheritance chain begins at ffmpeg/base.yaml; family and exact-version
documents override it. Inspect read_spec(target) for the effective configuration
and source paths. Recursive maps merge, lists replace, null deletes keys.

- source: upstream repository, ref, SHA512. Existing source identity is immutable.
- patches: ordered paths relative to patches/. Child list replaces parent list.
- build: base_options, debug options, host dependencies, CMake defines.
- features: configure flags, pkg-config modules, native vcpkg dependency edges,
  platform/version constraints, license, requires/conflicts.
- define: named feature groups including all-lgpl and all-gpl.
- dep_overrides: target-specific dependency alternatives, not arbitrary changes
  to shared third-party Port recipes.

Never edit base.yaml or unrelated inherited documents. Even a change to the
target family YAML is rejected if another existing version's resolved
configuration changes. Keep all required features and the license mode.
GPL-only features require explicit GPL licensing, nonfree builds cannot publish.
Use ffbuild validate to catch invalid conditions or dependency closure.
A source-less family template is not a released source version.
