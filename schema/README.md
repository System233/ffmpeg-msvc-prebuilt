# Metadata contracts

| Contract | Version | Purpose |
|---|---|---|
| Legacy Data YAML | v1 | Read-only migration of existing releases and standalone Develop assets. |
| Release catalog JSON | v2 | Root discovery index and one authoritative shard per stable version or Master year. |
| Native package format | 2 | First native ABI-qualified release format: Static CLI, Shared Binary plus differential Debug. |

The historical archives are immutable and have no native package format or ABI. No intermediate native package formats were released. A native variant requires the full ABI and format 2; it must contain Binary plus Debug for Shared, Binary only for Static. Legacy Develop is recognized by its asset key, not an invented format number.

The catalog schema changes only for incompatible storage changes. Adding fields before the first v2 cutover does not require another version. Package format identifies the archive layout and qualification gate; bump only when a deployed format must no longer be reused. The license policy has its own independently tracked revision in internal audit evidence.

## Catalog v2

`v2/index.schema.json` validates root `index.json`; `v2/shard.schema.json` validates `releases/<version>.json` and `master/<year>.json`. Root contains only shard discovery keys. A release and its asset records exist in one shard only. Stable shards contain explicit boolean `lts` (release-family classification, not a current support guarantee); snapshot shards use false. Migration writes this metadata directly. Run `python -m ffbuild refresh-lts --data-dir data` to refresh classifications without changing ZIPs, digests, tags or ABIs.

Legacy v1 YAML schemas are retained for historical interpretation. The legacy and current indexes must not coexist after cutover.

Optional variant `note: "legacy-lgpl-licensing"` identifies the historical LGPL licensing notice. Migration sets it only on historical LGPL variants, never on native ABI-qualified or GPL variants. The website resolves the note to localized text and the corresponding update-history section; it does not affect archive identity, digest or ABI reuse.
