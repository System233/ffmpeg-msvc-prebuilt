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


## Release catalog v2

`v2/index.schema.json` validates the root `index.json`; `v2/shard.schema.json`
validates `releases/<version>.json` and `master/<year>.json`.
The root contains only shard discovery keys. Each release and its asset records
exist in one shard only. Legacy v1 YAML remains readable for migration; v2 is
an explicit format cutover, not an additional index alongside v1.

Package format 4 adds the differential `debug` asset to catalog schema v2. Historical `develop` assets remain unchanged and standalone.
