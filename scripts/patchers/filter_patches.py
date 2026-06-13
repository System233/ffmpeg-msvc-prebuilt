"""
Filter out patches that don't apply to certain FFmpeg version families.
"""

# Patches known to not apply to specific families
_INCOMPATIBLE = {
    "5.1": {"0023-fix-qsv-init.patch"},  # Only applies to 4.x/6.x, not 5.x
}


def pre_patches(patches, ctx):
    family = ctx["family"]
    remove = _INCOMPATIBLE.get(family, set())
    for p in list(patches):
        if p in remove:
            patches.remove(p)
