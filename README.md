# FFmpeg MSVC Prebuilt — Web

React + Vite + React Router framework mode with build-time pre-rendering. No application server is required in production. The release catalog is the frontend data contract, including the required shard-level lts flag and support for package format 2 (Binary + Debug) and historical LGPL notices.

## Local development

Use Node 24 and pnpm 10. The data checkout must contain the release catalog (index.json, releases/, master/). Copy or check out the authoritative main schema at schema, or set CATALOG_DIR and SCHEMA_DIR to their locations.

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

English pages without a language prefix and Chinese pages under /zh/ are prerendered. Historic /en/ URLs redirect to canonical English pages while preserving queries and fragments when JavaScript is enabled; legacy VitePress .html redirects are generated only from genuine migrated tags and refs.

## Native-format regression

The synthetic fixture exercises same-day dated batch ordering, incomplete variant sets, nonfree configuration, reused asset filenames, lazy data loading, old links, explicit LTS metadata and differential Debug packages. It is never production data.

```sh
pnpm exec tsx scripts/test-catalog.ts
CATALOG_DIR=.generated/fixture-data CATALOG_FIXTURE=1 pnpm build
CATALOG_FIXTURE=1 pnpm exec playwright test tests/e2e/native.spec.ts
pnpm build
```

PowerShell: use $env:CATALOG_DIR and $env:CATALOG_FIXTURE, then remove these environment variables before the final production build. CI runs the fixture first, then replaces its build with the production snapshot before uploading the Pages artifact.

## Deployment

The same Pages workflow is maintained on main, web and data. It validates the release catalog against the authoritative Schema before building. Invalid or missing data fails the build and does not replace the deployed site.

## UI

The searchable version picker uses Base UI Combobox with compact inline filter tags and adaptive popup positioning. The download area distinguishes legacy Develop archives from differential Debug add-ons. Detail pages use a responsive download matrix and return controls that follow confirmed in-site history, otherwise linking to the parent page. UI messages are maintained in app/i18n/messages with matching typed keys and interpolation parameters. Documentation and FAQ are maintained in docs/en and docs/zh as Markdown, with syntax highlighting at build time. The shared UI includes responsive navigation, system/light/dark themes, accessible download links and feedback for clipboard failures. Automated accessibility checks cover the homepage, release list, release detail and guide.
