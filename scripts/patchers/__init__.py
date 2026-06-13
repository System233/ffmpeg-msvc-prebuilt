"""
Patcher plugin system for generate_port.py.

Each patcher is a .py file in this directory that implements any subset of
these hooks:

    post_extract(features, ctx)    → modify feature dict in-place
    pre_deps(deps, ctx)            → modify host dependency list in-place
    pre_defaults(defaults, ctx)    → modify default-features list in-place
    post_deps(deps, ctx)           → modify (non-host) dependency list in-place
    post_generate(port_dir, ctx)   → modify generated port directory (rare)
    pre_patches(patches, ctx)      → modify patch list in-place
    post_options(opts, ctx)        → populate opts dict with base/debug flags

ctx is a dict with keys: version, family, major, minor, patch
"""

import importlib
from pathlib import Path
from typing import Callable

HOOKS = ("post_extract", "pre_deps", "pre_defaults", "post_generate", "post_deps", "pre_patches", "post_options")


def discover() -> dict[str, list[Callable]]:
    """Scan scripts/patchers/*.py, return {hook: [fn, ...]}."""
    registry = {h: [] for h in HOOKS}
    here = Path(__file__).parent
    for f in sorted(here.glob("*.py")):
        if f.name.startswith("_"):
            continue
        mod = importlib.import_module(f"patchers.{f.stem}")
        for hook in HOOKS:
            fn = getattr(mod, hook, None)
            if callable(fn):
                registry[hook].append(fn)
    return registry


def run(hook: str, obj, ctx: dict):
    """Run all patchers for a given hook. obj is mutated in-place."""
    registry = discover()
    for fn in registry.get(hook, []):
        fn(obj, ctx)
