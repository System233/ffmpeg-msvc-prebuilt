# FFmpeg MSVC Prebuilt — Web

React + Vite + React Router framework mode with build-time pre-rendering. No application server is required in production. Data V2 is the sole contract of the new frontend, including the required shard-level lts flag and support for package format 2 (Binary + Debug) and historical LGPL notices.

## Local development

Use Node 24 and pnpm 10. The data checkout must contain the V2 catalog (index.json, releases/, master/). Copy or check out the authoritative main schema at schema/v2, or set CATALOG_DIR and SCHEMA_DIR to their locations.

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm build
pnpm typecheck
pnpm test
pnpm exec playwright install chromium
pnpm test:e2e
pnpm exec tsx scripts/measure.ts
```

Set BASE_URL to /ffmpeg-msvc-prebuilt/ for the GitHub Pages project subpath. Set VITE_SITE_URL and VITE_GITHUB_REPO_URL for a different deployment or repository. The build validates the complete snapshot, generates schema types, emits pages to build/client, and publishes the original data shards alongside HTML. The home page embeds only the initial release and compact variant choices; other versions are loaded from the deployed JSON shards on demand. LTS is read directly from the authoritative metadata, never inferred from version numbers. Use BUILD_DIR, PREVIEW_ROOT and PORT to isolate local build and test outputs.

The historic /en/ and /zh/ paths remain public. English pages without a language prefix are canonical; legacy VitePress .html redirects are generated only from genuine migrated tags and refs.

## Native-format regression

The synthetic fixture exercises same-day dated batch ordering, incomplete variant sets, nonfree configuration, reused asset filenames, lazy data loading, old links, explicit LTS metadata and differential Debug packages. It is never production data.

```sh
pnpm exec tsx scripts/test-catalog.ts
CATALOG_DIR=.generated/fixture-data CATALOG_FIXTURE=1 pnpm build
CATALOG_FIXTURE=1 pnpm exec playwright test tests/e2e/native.spec.ts
pnpm build
```

PowerShell: use $env:CATALOG_DIR and $env:CATALOG_FIXTURE, then remove these environment variables before the final production build. CI runs the fixture first, then replaces its build with the production snapshot before uploading the Pages artifact.

## Deployment cutover

The identical Pages workflow must be synchronized across main, web and data. The workflow uses the frontend's catalogSchema marker and Data V2 index to detect compatible pairs; during cutover, incompatible pairs deliberately skip upload and deployment and retain the existing live site. An unsupported schema, corrupt JSON, or missing catalog fails closed. The new frontend itself has no legacy YAML reader.

Before switching the production branches:
1. Confirm the remote data head still matches the reviewed migration source. If not, regenerate and review the migration against the latest data.
2. Drain any running publication, recovery and retention writers. Use a controlled maintenance window; do not allow legacy and V2 writers to modify data concurrently.
3. Apply the reviewed main code and workflow, the reviewed data migration and workflow, and the reviewed web code and workflow in a coordinated cutover. Ensure the new main schema supports format 2 and historical LGPL notices, and requires lts, and that all Data V2 shards contain the authoritative lts flag, before both data and web switch; keep writers paused until all three branches are ready.
4. Trigger Pages once against the final branch heads and check build, deployment, public HTML, .data files, JSON, and downloads.
5. Resume the normal publication and retention schedule only once the V2 writer and data agree.

If the frontend build or deployment fails, the existing Pages publication is not replaced. Do not force-push or restore the old data after new V2 releases are written; coordinate any rollback of the producer with the catalog and preserve published release assets.

## UI

The searchable version picker uses Base UI Combobox with compact inline filter tags and adaptive popup positioning. The download area distinguishes legacy Develop archives from differential Debug add-ons. Detail pages use a responsive download matrix and return controls that follow confirmed in-site history, otherwise linking to the parent page. Documentation and FAQ are available in English and Chinese, with syntax highlighting at build time. The shared UI includes responsive navigation, system/light/dark themes, accessible download links and feedback for clipboard failures. Automated accessibility checks cover the homepage, release list, release detail and guide.
