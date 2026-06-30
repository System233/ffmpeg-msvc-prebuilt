import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'
import yaml from 'js-yaml'

export interface ReleaseIndexItem {
  id: string
  version: string
  major: string
  revision: number | null
  lts: boolean
  snapshot: boolean
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
  develop_download_url?: string
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

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const webDir = path.resolve(scriptDir, '../..')
const outputDir = path.resolve(webDir, '.vitepress', 'generated')
const releasesDir = path.join(outputDir, 'releases')

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
      if (vdir === 'variants') continue
      const versionYaml = path.join(majorPath, vdir, 'version.yaml')
      if (fs.existsSync(versionYaml)) {
        results.push({ major, filePath: versionYaml })
      }
    }
  }

  return results
}

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
    const downloadBase = String(raw.release_url ?? '').replace(
      '/releases/tag/',
      '/releases/download/',
    )

    return {
      arch: String(v.arch ?? ''),
      triplet: String(v.triplet ?? ''),
      linkage: String(v.linkage ?? ''),
      license: String(v.license ?? ''),
      download_url: binaryFile ? `${downloadBase}/${binaryFile}` : '',
      develop_download_url:
        developRaw && String(developRaw?.file ?? '')
          ? `${downloadBase}/${String(developRaw.file)}`
          : undefined,
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
    snapshot: isSnapshot(String(raw.version ?? '')),
    ffmpeg_ref: String(raw.ffmpeg_ref ?? ''),
    release_tag: String(raw.release_tag ?? ''),
    release_url: String(raw.release_url ?? ''),
    created: String(raw.created ?? ''),
    updated: String(raw.updated ?? ''),
    variant_count: Number(raw.variant_count ?? variants.length),
    total_variants: archs.length * licenses.length * linkages.length,
    complete: Boolean(raw.complete ?? false),
    archs,
    licenses,
    linkages,
    variants,
  }
}

function isSnapshot(version: string): boolean {
  return !/^\d+(\.\d+)*$/.test(version)
}

function parseVersionNums(version: string): number[] {
  const m = version.match(/^(\d+(?:\.\d+)*)/)
  if (!m) return []
  return m[1].split('.').map(Number)
}

function compareVersions(a: string, b: string): number {
  const ap = parseVersionNums(a)
  const bp = parseVersionNums(b)
  const n = Math.max(ap.length, bp.length)
  for (let i = 0; i < n; i++) {
    const va = ap[i] ?? 0
    const vb = bp[i] ?? 0
    if (va !== vb) return va - vb
  }
  return 0
}

function timestampComment(): string {
  const now = new Date()
  const iso = now
    .toISOString()
    .replace('T', ' ')
    .replace(/\.\d{3}Z/, ' Z')
  return `// Generated on ${iso}`
}

function toJSON(obj: unknown): string {
  return JSON.stringify(obj, null, 2)
}

function safeFilename(id: string): string {
  return id.replace(/[^a-zA-Z0-9._-]/g, '_')
}

const INDEX_TYPE_DEFS = `
export interface ReleaseIndexItem {
  id: string
  version: string
  major: string
  revision: number | null
  lts: boolean
  snapshot: boolean
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
  develop_download_url?: string
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
  snapshot: boolean
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

export function main(): void {
  console.log('=== generate-content ===')
  console.log(`Script dir : ${scriptDir}`)
  console.log(`Web dir    : ${webDir}`)
  console.log(`Output dir : ${outputDir}`)
  console.log(`Data dir   : ${dataDir ?? '(not found – will use empty defaults)'}`)
  console.log()

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

  releases.sort((a, b) => {
    // Stable first, snapshots last
    if (a.snapshot !== b.snapshot) return a.snapshot ? 1 : -1
    // Within same group, sort by semantic version descending
    return compareVersions(b.version, a.version)
  })

  const releasesIndex: ReleaseIndexItem[] = releases.map((r) => {
    const { variants: _v, ...rest } = r
    return rest as ReleaseIndexItem
  })

  const releasesByMajor: Record<string, ReleaseIndexItem[]> = {}
  for (const item of releasesIndex) {
    const m = item.major
    if (!releasesByMajor[m]) releasesByMajor[m] = []
    releasesByMajor[m].push(item)
  }

  const latestRelease: ReleaseIndexItem | null =
    releasesIndex.find(r => !r.snapshot) ?? null

  const majors = Object.keys(releasesByMajor).sort()

  fs.mkdirSync(releasesDir, { recursive: true })

  const stamp = timestampComment()
  const NL = '\n'

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

  console.log()
  console.log('=== Summary ===')
  console.log(`  Releases found : ${releases.length}`)
  console.log(`  Files generated: ${1 + releaseFileCount} (1 index + ${releaseFileCount} release file(s))`)
  console.log(`  Majors         : ${majors.length > 0 ? majors.join(', ') : '(none)'}`)
  if (latestRelease) {
    console.log(`  Latest release : ${latestRelease.id} (${latestRelease.major})`)
  }
  console.log('=== Done ===')

  // ---- 5. Generate Feature Reference ----------------------------------------

  generateFeatureReference()
}

// ---------------------------------------------------------------------------
// Feature Reference generation (from ffmpeg/base.yaml)
// ---------------------------------------------------------------------------

interface FeatureDef {
  flag?: string
  pkgconfig?: string
  description?: string
  depends?: string[]
  platform?: string
  version?: string
}

const featureGroups: Record<string, string[]> = {
  'Core Libraries': ['avcodec', 'avdevice', 'avformat', 'avfilter', 'swresample', 'swscale', 'avresample', 'postproc'],
  'License Flags': ['license-gpl', 'license-nonfree'],
  'Compression / Text / Fonts': ['zlib', 'bzip2', 'lzma', 'iconv', 'freetype', 'fribidi', 'fontconfig', 'harfbuzz', 'ass'],
  Audio: ['opus', 'vorbis', 'theora', 'speex', 'mp3lame', 'soxr', 'openmpt', 'ilbc', 'modplug', 'tesseract', 'gme'],
  'Video / Image': ['dav1d', 'aom', 'vpx', 'webp', 'openjpeg', 'snappy', 'openh264', 'lensfun', 'jxl', 'shaderc', 'svtav1', 'vvenc'],
  'Network / Graphics / Container': ['sdl2', 'xml2', 'srt', 'ssh', 'openssl', 'zmq', 'mysofa', 'bluray'],
  'Hardware Acceleration': ['nvcodec', 'amf', 'qsv', 'mfx', 'vulkan', 'opencl', 'opengl'],
  'Windows Platform': ['w32threads', 'd3d11va', 'd3d12va', 'dxva2', 'mediafoundation', 'pthreads'],
  GPL: ['x264', 'x265', 'dvdnav', 'dvdread'],
  'Non-free': ['fdk-aac'],
  'Meta Features': ['static', 'ffplay', 'ffmpeg', 'ffprobe', 'base', 'app', 'windows-hw', 'all', 'lgpl', 'all-lgpl', 'gpl', 'all-gpl', 'nonfree', 'all-nonfree'],
}

function generateFeatureReference(): void {
  const baseYamlPath = path.resolve(webDir, '..', 'ffmpeg', 'base.yaml')
  if (!fs.existsSync(baseYamlPath)) {
    console.log('  ⚠  ffmpeg/base.yaml not found, skipping feature reference')
    return
  }

  const content = fs.readFileSync(baseYamlPath, 'utf-8')
  const raw = yaml.load(content) as Record<string, unknown> | null
  if (!raw?.features || typeof raw.features !== 'object') {
    console.log('  ⚠  No features found in base.yaml')
    return
  }

  const allFeatures = raw.features as Record<string, Record<string, unknown>>
  const NL = '\n'

  function loadLocales(lang: string): Record<string, unknown> {
    const p = path.join(webDir, 'locales', `${lang}.json`)
    return JSON.parse(fs.readFileSync(p, 'utf-8'))
  }

  const enLocale = loadLocales('en')
  const zhLocale = loadLocales('zh')
  const refEn = enLocale.reference as Record<string, string>
  const refZh = zhLocale.reference as Record<string, string>

  const frontmatter = `---\ntitle: ${refEn.title}\ndescription: ${refEn.description}\n---\n\n# ${refEn.heading}\n\n`
  const zhFrontmatter = `---\ntitle: ${refZh.title}\ndescription: ${refZh.description}\n---\n\n# ${refZh.heading}\n\n`

  function escapeMd(text: string): string {
    return text.replace(/\|/g, '\\|')
  }

  function fmtDep(dep: unknown): string {
    const d = String(dep)
    if (d.startsWith('@')) return `\`${d}\``
    return `\`${d}\``
  }

  function fmtFlag(flag: unknown): string {
    if (!flag) return '—'
    return `\`${flag}\``
  }

  function fmtDesc(desc: unknown): string {
    if (!desc) return '—'
    return escapeMd(String(desc))
  }

  function fmtPlatform(p: unknown): string {
    if (!p) return '—'
    return `\`${p}\``
  }

  function fmtVersion(v: unknown): string {
    if (!v) return '—'
    return `\`${v}\``
  }

  const sections: string[] = []

  for (const [groupName, featureNames] of Object.entries(featureGroups)) {
    const rows: string[] = []
    for (const name of featureNames) {
      const f = allFeatures[name]
      if (!f) continue
      rows.push(
        `| \`${name}\` | ${fmtFlag(f.flag)} | ${fmtDesc(f.description)} | ${f.depends?.length ? f.depends.map(fmtDep).join(', ') : '—'} | ${fmtPlatform(f.platform)} | ${fmtVersion(f.version)} |`,
      )
    }
    if (rows.length === 0) continue
    sections.push(`## ${groupName}\n\n| Feature | Configure Flag | Description | Dependencies | Platform | Since |\n|---------|---------------|-------------|-------------|----------|-------|\n${rows.join(NL)}`)
  }

  // GPL / Non-free quick reference
  const gplFeatures: string[] = []
  const nonfreeFeatures: string[] = []
  const platformRestricted: string[] = []
  for (const [name, f] of Object.entries(allFeatures)) {
    const deps = (f.depends as string[]) || []
    if (deps.includes('@license-gpl')) gplFeatures.push(name)
    if (deps.includes('@license-nonfree')) nonfreeFeatures.push(name)
    if (f.platform) platformRestricted.push(name)
  }

  sections.push(
    '## License Summary\n\n'
    + `**GPL features** (require \`--enable-gpl\`): \`${gplFeatures.join('`, `')}\`\n\n`
    + `**Non-free features** (require \`--enable-nonfree\`): \`${nonfreeFeatures.join('`, `')}\`\n\n`
    + `**Platform-restricted features**: \`${platformRestricted.join('`, `')}\``,
  )

  const body = sections.join(`\n\n`)
  const docDir = path.join(webDir, 'docs')
  const enRef = path.join(docDir, 'en', 'reference.md')
  const zhRef = path.join(docDir, 'zh', 'reference.md')

  fs.mkdirSync(path.join(docDir, 'en'), { recursive: true })
  fs.mkdirSync(path.join(docDir, 'zh'), { recursive: true })
  fs.writeFileSync(enRef, frontmatter + body)
  fs.writeFileSync(zhRef, zhFrontmatter + body)

  console.log(`  ✓  Feature reference written to docs/en|zh/reference.md (${allFeatures ? Object.keys(allFeatures).length : 0} features)`)
}
