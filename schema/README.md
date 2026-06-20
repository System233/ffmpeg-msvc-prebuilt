# Schema

This directory contains JSON Schema definitions describing the structure of YAML
data files used in the build & release pipeline.

## Versioning

Each subdirectory (`v1/`, `v2/`, …) corresponds to a `schema_version` value in
the release YAML files under `data/`.

| `schema_version` | Directory | Description |
|---|---|---|
| 1 | `v1/` | Initial structured schema — `assets.binary` nested format with optional `assets.develop` |

## Files

| Schema file | Validates | Source / Consumer |
|---|---|---|
| `variant.schema.json` | `.var.yaml` | Produced by `package_release.py`, consumed by `import_yaml.py` |
| `release.schema.json` | `data/**/*.yaml` | Produced by `import_yaml.py`, consumed by `web/scripts/generate-content.ts` |

## When to bump `schema_version`

Increment `schema_version` when making **backward-incompatible** structural
changes to the release YAML files (adding optional fields does not require a
bump). Create a new subdirectory `v<N>/` for the new version.
