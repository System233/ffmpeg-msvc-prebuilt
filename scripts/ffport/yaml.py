"""YAML loading and chain resolution."""

import re
import sys
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    sys.exit("ERROR: pip install pyyaml required")

REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_DIR = REPO_ROOT / "ffmpeg"


def load_yaml(name: str) -> dict:
    """Load a YAML file from the ffmpeg directory by name (without .yaml)."""
    path = YAML_DIR / f"{name}.yaml"
    if not path.is_file():
        print(f"ERROR: YAML file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return _yaml.safe_load(f)


def resolve_chain(name: str) -> tuple[list[dict], str]:
    """
    Resolve extends chain from base up to a YAML file.

    If *name* matches ``X.Y`` or ``X.Y.Z``, loads the version chain
    (family + optional patch YAML).  Otherwise loads ``{name}.yaml``
    and follows its ``extends`` chain.

    Returns ``(docs, label)`` where ``docs = [base, ..., <leaf>]``.
    """
    if re.match(r'^\d+\.\d+(?:\.\d+)?$', name):
        return _resolve_version_chain(name)
    return _resolve_custom_chain(name)


def _resolve_version_chain(version: str) -> tuple[list[dict], str]:
    """Load chain for a standard ``X.Y[.Z]`` version string."""
    parts = version.split(".")
    major, minor = parts[0], parts[1]
    family = f"{major}.{minor}"

    docs = [load_yaml("base")]

    family_doc = load_yaml(family)
    parent = family_doc.get("extends", "base")

    if parent != "base":
        parent_docs, _ = resolve_chain(parent)
        docs = [docs[0]] + parent_docs[1:]
    else:
        docs = [docs[0]]

    docs.append(family_doc)

    if len(parts) == 3:
        patch_path = YAML_DIR / f"{version}.yaml"
        if patch_path.is_file():
            patch_doc = load_yaml(version)
            docs.append(patch_doc)

    return docs, family


def _resolve_custom_chain(name: str) -> tuple[list[dict], str]:
    """Load chain for an arbitrary YAML file (e.g. ``master``)."""
    doc = load_yaml(name)
    parent = doc.get("extends", "base")

    docs = [load_yaml("base")]
    if parent != "base":
        parent_docs, _ = resolve_chain(parent)
        docs = [docs[0]] + parent_docs[1:]

    docs.append(doc)
    return docs, name
