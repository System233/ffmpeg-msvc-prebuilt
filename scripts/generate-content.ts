import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'
import yaml from 'js-yaml'

// ---------------------------------------------------------------------------
// Public interfaces (exported for external consumption / type imports)
// ---------------------------------------------------------------------------

export interface ReleaseIndexItem {
  id: string
  version: string
  major: string
  revision: number | null
  lts: boolean
  ffmpeg_ref: string
  release_tag: string
  release_url: string
  created: string
  updated: string
  variant_count: number
  total_variants: number
  complete: boolean
  archs: string[]
  licenses: string[]
  linkages: string[]
}

export interface AssetInfo {
  file: string
  size: number
  digest: string
}

export interface VariantData {
  arch: string
  triplet: string
  linkage: string
  license: string
  download_url: string
  assets: {
    binary: AssetInfo
    develop?: AssetInfo
  }
  features: string[]
  dependencies: string[]
}

export interface ReleaseData extends ReleaseIndexItem {
  variants: VariantData[]
}

// ---------------------------------------------------------------------------
// Path resolution
// ---------------------------------------------------------------------------

/** Absolute path to the directory this script lives in (web/scripts/). */
const scriptDir = path.dirname(fileURLToPath(import.meta.url))

/** Absolute path to the web/ directory (one level up from scripts/). */
const webDir = path.resolve(scriptDir, '..')

/** Output directory for generated files: web/.vitepress/generated/. */
const outputDir = path.resolve(webDir, '.vitepress', 'generated')

/** Sub-directory for per-release files. */
const releasesDir = path.join(outputDir, 'releases')

/**
 * Resolve the data/ directory.
 *
 * Two layouts are supported:
 *   1. CI:  data/ is checked out as web/data/ (sibling of scripts/)
 *   2. Local: data/ is at the repository root (parent of web/)
 *
 * We prefer ./data/ relative to process.cwd() (CI), then fall back to
 * ../data/ (local dev).  If neither exists, `dataDir` remains null and we
 * generate empty defaults.
 */
const cwd = process.cwd()
const dataSearchPaths = [
  path.join(cwd, 'data'),
  path.resolve(cwd, '..', 'data'),
]
let dataDir: string | null = null
for (const p of dataSearchPaths) {
  if (fs.existsSync(p)) {
    dataDir = p
    break
  }
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/**
 * Scan a resolved data/ directory and return metadata for every
 * data/{major}/{version}/version.yaml file, skipping old-style build-index
 * and variants directories.
 */
function scanYamlFiles(
  dataDirPath: string,
): Array<{ major: string; filePath: string }> {
  const results: Array<{ major: string; filePath: string }> = []

  const majorDirs = fs.readdirSync(dataDirPath, { withFileTypes: true })
  for (const majorDir of majorDirs) {
    if (!majorDir.isDirectory()) continue
    const major = majorDir.name
    const majorPath = path.join(dataDirPath, major)

    let versionDirs: string[]
    try {
      versionDirs = fs.readdirSync(majorPath)
    } catch {
      continue
    }

    for (const vdir of versionDirs) {
      if (vdir === 'variants') continue // skip old-style variants dir
      const versionYaml = path.join(majorPath, vdir, 'version.yaml')
      if (fs.existsSync(versionYaml)) {
        results.push({ major, filePath: versionYaml })
      }
    }
  }

  return results
}

/**
 * Derive a stable release identifier from parsed YAML data.
 *
 * Unified format: "{ffmpeg_ref}-r{revision}"  (e.g. "n8.1.1-r2", "n8.2-dev-1-gabc1234-r0")
 */
function computeReleaseId(
  raw: {
    version: string
    revision: number | null
    ffmpeg_ref: string
  },
  _major: string,
): string {
  return `${raw.ffmpeg_ref || 'unknown'}-r${raw.revision ?? 0}`
}

/**
 * Parse a raw YAML object into a fully typed ReleaseData structure,
 * computing derived fields (archs, licenses, linkages) on the fly.
 */
function parseRelease(
  id: string,
  major: string,
  raw: Record<string, unknown>,
): ReleaseData {
  const variantsRaw = (raw.variants as Array<Record<string, unknown>>) || []

  const variants: VariantData[] = variantsRaw.map((v) => {
    const assetsRaw = v.assets as Record<string, unknown> | undefined
    const binaryRaw = assetsRaw?.binary as Record<string, unknown> | undefined
    const developRaw = assetsRaw?.develop as Record<string, unknown> | undefined

    const binaryFile = String(binaryRaw?.file ?? '')
    const binarySize = Number(binaryRaw?.size ?? 0)
    const binaryDigest = String(binaryRaw?.digest ?? '')

    return {
      arch: String(v.arch ?? ''),
      triplet: String(v.triplet ?? ''),
      linkage: String(v.linkage ?? ''),
      license: String(v.license ?? ''),
      download_url: binaryFile ? `${raw.release_url || ''}/${binaryFile}` : '',
      assets: {
        binary: {
          file: binaryFile,
          size: binarySize,
          digest: binaryDigest,
        },
        ...(developRaw
          ? {
              develop: {
                file: String(developRaw?.file ?? ''),
                size: Number(developRaw?.size ?? 0),
                digest: String(developRaw?.digest ?? ''),
              },
            }
          : {}),
      },
      features: (v.features as string[]) || [],
      dependencies: (v.dependencies as string[]) || [],
    }
  })

  const archs = [...new Set(variants.map((v) => v.arch))].sort()
  const licenses = [...new Set(variants.map((v) => v.license))].sort()
  const linkages = [...new Set(variants.map((v) => v.linkage))].sort()

  const rawRevision = raw.revision
  const revision =
    rawRevision !== null && rawRevision !== undefined
      ? Number(rawRevision)
      : null

  return {
    id,
    version: String(raw.version ?? ''),
    major,
    revision,
    lts: Boolean(raw.lts ?? false),
    ffmpeg_ref: String(raw.ffmpeg_ref ?? ''),
    release_tag: String(raw.release_tag ?? ''),
    release_url: String(raw.release_url ?? ''),
    created: String(raw.created ?? ''),
    updated: String(raw.updated ?? ''),
    variant_count: Number(raw.variant_count ?? variants.length),
    total_variants: Number(raw.total_variants ?? 0),
    complete: Boolean(raw.complete ?? false),
    archs,
    licenses,
    linkages,
    variants,
  }
}

/** Return an ISO-8601 timestamp suitable for a generated-file comment. */
function timestampComment(): string {
  const now = new Date()
  // Format: "2026-06-15 12:34:56 Z"
  const iso = now
    .toISOString()
    .replace('T', ' ')
    .replace(/\.\d{3}Z/, ' Z')
  return `// Generated on ${iso}`
}

/** JSON stringify with 2-space indentation. */
function toJSON(obj: unknown): string {
  return JSON.stringify(obj, null, 2)
}

/** Sanitize a release ID so it is safe for use as a filename. */
function safeFilename(id: string): string {
  return id.replace(/[^a-zA-Z0-9._-]/g, '_')
}

// ---------------------------------------------------------------------------
// TypeScript source snippets (inlined in generated files)
// ---------------------------------------------------------------------------

const INDEX_TYPE_DEFS = `
export interface ReleaseIndexItem {
  id: string
  version: string
  major: string
  revision: number | null
  lts: boolean
  ffmpeg_ref: string
  release_tag: string
  release_url: string
  created: string
  updated: string
  variant_count: number
  total_variants: number
  complete: boolean
  archs: string[]
  licenses: string[]
  linkages: string[]
}
`

const RELEASE_TYPE_DEFS = `
export interface AssetInfo {
  file: string
  size: number
  digest: string
}

export interface VariantData {
  arch: string
  triplet: string
  linkage: string
  license: string
  download_url: string
  assets: {
    binary: AssetInfo
    develop?: AssetInfo
  }
  features: string[]
  dependencies: string[]
}

export interface ReleaseData {
  id: string
  version: string
  major: string
  revision: number | null
  lts: boolean
  ffmpeg_ref: string
  release_tag: string
  release_url: string
  created: string
  updated: string
  variant_count: number
  total_variants: number
  complete: boolean
  archs: string[]
  licenses: string[]
  linkages: string[]
  variants: VariantData[]
}
`

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main(): void {
  console.log('=== generate-content ===')
  console.log(`Script dir : ${scriptDir}`)
  console.log(`Web dir    : ${webDir}`)
  console.log(`Output dir : ${outputDir}`)
  console.log(`Data dir   : ${dataDir ?? '(not found – will use empty defaults)'}`)
  console.log()

  // ---- 1. Scan & parse YAML files -----------------------------------------

  const yamlFiles = dataDir ? scanYamlFiles(dataDir) : []
  console.log(`Found ${yamlFiles.length} YAML file(s)`)

  const releases: ReleaseData[] = []
  for (const { major, filePath } of yamlFiles) {
    try {
      const content = fs.readFileSync(filePath, 'utf-8')
      const raw = yaml.load(content) as Record<string, unknown> | null
      if (!raw || typeof raw !== 'object') {
        console.warn(`  ⚠  Skipping empty/invalid YAML: ${filePath}`)
        continue
      }

      const id = computeReleaseId(
        raw as { version: string; revision: number | null; ffmpeg_ref: string },
        major,
      )
      const release = parseRelease(id, major, raw)
      releases.push(release)
      console.log(`  ✓  ${id.padEnd(28)} (${major})`)
    } catch (err) {
      console.warn(
        `  ⚠  Failed to parse ${filePath}: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }

  // ---- 2. Sort (descending by created) & build derived structures ----------

  releases.sort((a, b) => {
    const aTime = new Date(a.created).getTime()
    const bTime = new Date(b.created).getTime()
    if (isNaN(aTime) && isNaN(bTime)) return 0
    if (isNaN(aTime)) return 1
    if (isNaN(bTime)) return -1
    return bTime - aTime
  })

  // Strip variants for the index list
  const releasesIndex: ReleaseIndexItem[] = releases.map((r) => {
    const { variants: _v, ...rest } = r
    return rest as ReleaseIndexItem
  })

  // Group by major version
  const releasesByMajor: Record<string, ReleaseIndexItem[]> = {}
  for (const item of releasesIndex) {
    const m = item.major
    if (!releasesByMajor[m]) releasesByMajor[m] = []
    releasesByMajor[m].push(item)
  }

  const latestRelease: ReleaseIndexItem | null =
    releasesIndex.length > 0 ? releasesIndex[0] : null

  const majors = Object.keys(releasesByMajor).sort()

  // ---- 3. Write output files -----------------------------------------------

  // Ensure output directories exist
  fs.mkdirSync(releasesDir, { recursive: true })

  const stamp = timestampComment()
  const NL = '\n'

  // -------- releases-index.ts --------

  const indexContent = [
    stamp,
    '// This file is auto-generated. Do not edit manually.',
    '',
    INDEX_TYPE_DEFS.trim(),
    '',
    `export const releasesIndex: ReleaseIndexItem[] = ${toJSON(releasesIndex)}`,
    '',
    `export const releasesByMajor: Record<string, ReleaseIndexItem[]> = ${toJSON(releasesByMajor)}`,
    '',
    `export const latestRelease: ReleaseIndexItem | null = ${toJSON(latestRelease)}`,
    '',
    `export const majors: string[] = ${toJSON(majors)}`,
    '',
  ].join(NL)

  fs.writeFileSync(path.join(outputDir, 'releases-index.ts'), indexContent)
  console.log(`\n  ✓  ${path.join(outputDir, 'releases-index.ts')}`)

  // -------- per-release files --------

  let releaseFileCount = 0
  for (const release of releases) {
    const id = release.id
    const filename = safeFilename(id)
    const filePath = path.join(releasesDir, `${filename}.ts`)

    const releaseContent = [
      stamp,
      '// This file is auto-generated. Do not edit manually.',
      '',
      RELEASE_TYPE_DEFS.trim(),
      '',
      `const data: ReleaseData = ${toJSON(release)}`,
      '',
      'export default data',
      '',
    ].join(NL)

    fs.writeFileSync(filePath, releaseContent)
    releaseFileCount++
  }

  console.log(`  ✓  ${releaseFileCount} release file(s) written to ${releasesDir}`)

  // ---- 4. Summary ----------------------------------------------------------

  console.log()
  console.log('=== Summary ===')
  console.log(`  Releases found : ${releases.length}`)
  console.log(`  Files generated: ${1 + releaseFileCount} (1 index + ${releaseFileCount} release file(s))`)
  console.log(`  Majors         : ${majors.length > 0 ? majors.join(', ') : '(none)'}`)
  if (latestRelease) {
    console.log(`  Latest release : ${latestRelease.id} (${latestRelease.major})`)
  }
  console.log('=== Done ===')
}

main()
