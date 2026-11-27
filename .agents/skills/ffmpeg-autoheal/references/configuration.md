# Resolve and compare actual configuration

Use the repository's resolver; do not implement your own YAML inheritance. Run from the checkout:

    python -c "import json; from ffbuild.spec import read_spec; c,p=read_spec('master'); print(json.dumps(c,indent=2)); print(*p,sep='\n')"

Replace master with the bound target. read_spec returns effective configuration and ordered source documents. It recursively merges maps, replaces lists and removes keys set to null. A stable X.Y.Z release loads its family first and then its exact document; Master follows its actual extends chain. Preserve the complete effective patch list when overriding an inherited list.

Read the effective source, patches, build options, features, define and dep_overrides. Inspect the generated vcpkg.json, features.cmake, constraints.cmake, portfile.cmake and copied builder. Trace requested Feature roots to effective closure using ffbuild.targets.compile_target and the exact source version/triplet. The Build Plan lists planned Features, not proof that a failed binary contained them.

To compare a baseline and candidate, use ffbuild.spec.read_spec with directory=Path(<baseline ffmpeg directory>) and directory=Path(<candidate ffmpeg directory>) in a scratch script. Save the baseline configuration before changes. Use ffbuild.targets.load_targets() and compile_target(config, version, target) for the entire configured matrix (for Master use the numeric release prefix of the pinned describe, without leading n). Compare package, triplet, features, license and linkage, along with effective dependency edges in the generated manifests and configure options. Record the intended difference and justify every other changed field. Preserve functionality; identical feature names alone do not prove identical behavior.

Only change the target's YAML; never edit inherited shared YAML. Directly referencing a new patch requires the full effective ordered list, not an appended fragment that drops inherited patches. Changing a dependency selection must be justified against the actual registry/overlay and preserve the requested capability and license. Do not change source identity, policy checks or target list. Use ffbuild validate for static checks; it is not a build and does not generate a pinned Master candidate on its own.
