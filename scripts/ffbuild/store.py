"""Project published records onto the reusable release index fields."""

# Data is a Release index, not a CI artifact or compliance database.
# Explicit projection prevents newly added Worker fields leaking into Data.
_INDEX_FIELDS = frozenset("""
    variant_id version arch triplet linkage license lts ffmpeg_ref build_date
    assets features dependencies package_spec port abi_hash expected_variants
    release_date publication_date channel source_commit package_format
""".split())


def release_index(record: dict) -> dict:
    result = {key: value for key, value in record.items() if key in _INDEX_FIELDS}
    if "assets" in result:
        result["assets"] = {kind: {key: value for key, value in asset.items()
                                    if key in ("file", "size", "digest")}
                            for kind, asset in result["assets"].items()
                            if kind in ("binary", "develop")}
    return result
