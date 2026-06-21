"""ffport — Generate vcpkg ports for FFmpeg from YAML specification.

Usage:
  ffport generate <yaml> [--version VER] [-r REF] [--sha512 SHA512]
                        [-n <name>] [-o <dir>] [--build-date <YYYYMMDD>]
  ffport list
  ffport deps
"""

import argparse
import shutil
import sys
from pathlib import Path

from . import builder, features, merge, patches, templates, version as ver_mod, yaml, deps_port

REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_DIR = REPO_ROOT / "ffmpeg"


def cmd_generate(args):
    """Generate vcpkg port for a specific version."""
    if not args.yaml:
        print("error: specify a YAML name", file=sys.stderr)
        sys.exit(1)
    _generate(args.yaml, args.version, args.sha512, args.build_date,
              args.port_name, args.output, args.ref)


def cmd_list(args):
    """List available version YAML files."""
    found = False
    for f in sorted(YAML_DIR.glob("*.yaml")):
        if f.stem in ("base", "master"):
            continue
        print(f.stem)
        found = True
    if not found:
        print("(no version YAML files found)", file=sys.stderr)


def cmd_deps(args):
    """Generate the ffmpeg-deps virtual port."""
    deps_port.generate_deps_port()


def cmd_get_revision(args):
    """Print the revision number from a version YAML chain."""
    docs, _ = yaml.resolve_chain(args.yaml)
    merged = {}
    for doc in docs:
        merged = merge.deep_merge(merged, doc)
    print(merged.get("revision", 0))


def _generate(yaml_name, version=None, sha512=None, build_date=None,
              port_name="ffmpeg", output=None, ref=None):
    """Generate port directory for a given YAML config and optional version."""
    # 1. Resolve YAML chain
    docs, family = yaml.resolve_chain(yaml_name)
    print(f"  Family: {family}")

    # 2. Deep merge
    merged = {}
    for doc in docs:
        merged = merge.deep_merge(merged, doc)

    # 3. Version resolution (--version takes precedence, otherwise derive from YAML filename)
    import re as _re

    parsed = None
    if version:
        parsed = ver_mod.parse_version(version)
        final_ver = parsed["version"]
    elif _re.match(r'^\d+\.\d+(?:\.\d+)?$', yaml_name):
        final_ver = yaml_name
    else:
        print("error: cannot determine version, use --version", file=sys.stderr)
        sys.exit(1)

    display_ver = (parsed.get("display_ver") if parsed else None)
    if not display_ver:
        display_ver = f"n{final_ver}"

    # 4. REF resolution (priority: --ref > commit from describe > n{base_version} > n{final_ver})
    if ref:
        source_ref = ref
    elif parsed and parsed.get("commit"):
        source_ref = parsed["commit"]
    elif parsed:
        source_ref = f"n{parsed['base_version']}"
    else:
        source_ref = f"n{final_ver}"

    # 5. SHA512 validation
    yaml_sha = merged.get("source", {}).get("sha512")
    need_sha = False
    if parsed and parsed.get("commit"):
        need_sha = True
    elif version is not None and version != yaml_name:
        need_sha = True
    elif not yaml_sha:
        need_sha = True

    if need_sha:
        if not sha512:
            print("error: --sha512 required", file=sys.stderr)
            sys.exit(1)
        if not _re.match(r'^[0-9a-f]{128}$', sha512):
            print(f"error: --sha512 must be 128-char hex, got {len(sha512)} chars",
                  file=sys.stderr)
            sys.exit(1)

    merged.setdefault("source", {})["ref"] = source_ref
    if sha512:
        merged["source"]["sha512"] = sha512
    elif yaml_sha:
        merged["source"]["sha512"] = yaml_sha

    # 6. Feature resolution
    base_ver = parsed.get("base_version", final_ver) if parsed else final_ver
    feats = features.resolve_features(merged, base_ver)
    print(f"  Features: {len(feats['features'])} resolved")

    source_section = merged.get("source", {})
    the_sha512 = source_section.get("sha512", "TODO")

    build_section = merged.get("build", {})
    host_deps_list = build_section.get("host_deps", [])
    dep_overrides_section = merged.get("dep_overrides", {})

    all_registry_names = set(merged.get("features", {}).keys())
    feature_deps, feature_refs, _ = features.collect_deps(
        feats["features"], dep_overrides_section, host_deps_list, all_registry_names)
    print(f"  Deps: {sum(len(v) for v in feature_deps.values())} packages")

    patches_list = merged.get("patches", [])
    print(f"  Patches: {len(patches_list)} files")

    revision = merged.get("revision", 0)
    print(f"  Revision: {revision}")

    output_dir = Path(output) if output else REPO_ROOT / "ports"
    port_dir = output_dir / port_name
    if port_dir.exists():
        shutil.rmtree(str(port_dir))
    port_dir.mkdir(parents=True)

    patch_names = patches.copy_patches(patches_list, port_dir)
    builder.copy_builder_files(port_dir)

    templates.generate_portfile(final_ver, the_sha512, build_section, patch_names, port_dir,
                                 revision=revision, source=source_section)
    templates.generate_vcpkg_json(final_ver, feats, feature_deps, feature_refs,
                                   host_deps_list, revision, merged, port_dir,
                                   port_name=port_name, display_ver=display_ver)
    templates.generate_features_cmake(merged.get("features", {}), port_dir, family)
    templates.generate_usage(port_dir)

    file_count = len(list(port_dir.iterdir()))
    print(f"  Generated {port_dir}/ ({file_count} files)")


def main():
    parser = argparse.ArgumentParser(
        prog="ffport",
        description="Generate vcpkg ports for FFmpeg from YAML specification.")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate vcpkg port")
    gen.add_argument("yaml", help="YAML config name (e.g. 8.1.1, master)")
    gen.add_argument("--version", default=None, help="Version override")
    gen.add_argument("-n", "--port-name", default="ffmpeg",
                     help="Port name (default: ffmpeg)")
    gen.add_argument("-o", "--output", default=None,
                     help="Output directory (default: ports/)")
    gen.add_argument("--sha512", default=None, help="Override SHA512")
    gen.add_argument("--build-date", default=None,
                     help="Build date YYYYMMDD")
    gen.add_argument("-r", "--ref", default=None,
                     help="Git ref for checkout")

    sub.add_parser("list", help="List available version YAML files")
    sub.add_parser("deps", help="Generate ffmpeg-deps virtual port")
    rev = sub.add_parser("get-revision", help="Print revision from a version YAML")
    rev.add_argument("yaml", help="Version stem (e.g. 8.1.1)")

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "deps":
        cmd_deps(args)
    elif args.command == "get-revision":
        cmd_get_revision(args)


if __name__ == "__main__":
    main()
