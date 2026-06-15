#!/usr/bin/env tsx
/**
 * render-locales.ts
 *
 * Walks src/ and generates en/ and zh/ directories by rendering .mustache
 * and .vue.mustache templates with locale data and copying non-mustache
 * files as-is.
 *
 * Usage:
 *   npx tsx scripts/render-locales.ts
 *
 * Requires:
 *   - mustache  (npm install mustache)
 */
import Mustache from 'mustache'
import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  existsSync,
  rmSync,
  cpSync,
} from 'node:fs'
import { join, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

// ---------------------------------------------------------------------------
// Path resolution
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const root = join(__dirname, '..')
const srcDir = join(root, 'src')

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Recursively count files in a directory tree.
 */
function countFiles(dir: string): number {
  let count = 0
  try {
    const entries = readdirSync(dir, { withFileTypes: true })
    for (const entry of entries) {
      const fullPath = join(dir, entry.name)
      if (entry.isDirectory()) {
        count += countFiles(fullPath)
      } else {
        count++
      }
    }
  } catch {
    // Directory may have been removed concurrently – ignore
  }
  return count
}

/**
 * Recursively walk `currentDir` (relative to `srcBase`) and either render
 * .mustache files through Mustache or copy other files verbatim into the
 * locale-specific output tree rooted at `outDirBase`.
 *
 * Directories named `public` are intentionally skipped – they are handled
 * separately by the caller via a raw recursive copy.
 */
function processDir(
  currentDir: string,
  outDirBase: string,
  srcBase: string,
  localeData: Record<string, unknown>,
  stats: { rendered: number; copied: number },
): void {
  const entries = readdirSync(currentDir, { withFileTypes: true })

  for (const entry of entries) {
    // Skip public directories – handled as a separate raw copy step
    if (entry.isDirectory() && entry.name === 'public') continue

    const srcPath = join(currentDir, entry.name)
    const relPath = relative(srcBase, srcPath)
    const outPath = join(outDirBase, relPath)

    if (entry.isDirectory()) {
      // Ensure output subdirectory exists, then recurse
      mkdirSync(outPath, { recursive: true })
      processDir(srcPath, outDirBase, srcBase, localeData, stats)
    } else if (entry.name.endsWith('.vue.mustache')) {
      // Render .vue.mustache template with locale data → .vue
      const template = readFileSync(srcPath, 'utf-8')
      const rendered = Mustache.render(template, localeData, {}, { tags: ['[[', ']]'] })

      // Output filename: strip .vue.mustache → .vue
      const outFile = outPath.replace(/\.vue\.mustache$/, '.vue')
      mkdirSync(dirname(outFile), { recursive: true })
      writeFileSync(outFile, rendered, 'utf-8')
      stats.rendered++
    } else if (entry.name.endsWith('.mustache')) {
      // Render .mustache template with locale data → .md
      const template = readFileSync(srcPath, 'utf-8')
      const rendered = Mustache.render(template, localeData, {}, { tags: ['[[', ']]'] })

      // Output filename: strip .mustache → .md
      const outFile = outPath.replace(/\.mustache$/, '.md')
      mkdirSync(dirname(outFile), { recursive: true })
      writeFileSync(outFile, rendered, 'utf-8')
      stats.rendered++
    } else {
      // Non-mustache file: copy verbatim
      mkdirSync(dirname(outPath), { recursive: true })
      writeFileSync(outPath, readFileSync(srcPath))
      stats.copied++
    }
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log('=== render-locales ===\n')

  // 1. Load locale JSON files via readFileSync + JSON.parse
  function loadLocale(lang: string): Record<string, unknown> {
    const filePath = join(root, 'locales', `${lang}.json`)
    const raw = readFileSync(filePath, 'utf-8')
    return JSON.parse(raw) as Record<string, unknown>
  }

  const locales: Record<string, Record<string, unknown>> = {
    en: loadLocale('en'),
    zh: loadLocale('zh'),
  }

  for (const [lang, localeData] of Object.entries(locales)) {
    const outDir = join(root, lang)

    // Clean slate: remove existing output directory if present
    if (existsSync(outDir)) {
      rmSync(outDir, { recursive: true })
    }
    mkdirSync(outDir, { recursive: true })

    const stats = { rendered: 0, copied: 0 }

    // 2. Walk src/ and render/copy files
    processDir(srcDir, outDir, srcDir, localeData, stats)

    // 3. Handle src/public/ separately – copy the entire directory as-is
    const publicDir = join(srcDir, 'public')
    if (existsSync(publicDir)) {
      const publicOutDir = join(outDir, 'public')
      cpSync(publicDir, publicOutDir, { recursive: true })
      const publicFiles = countFiles(publicDir)
      stats.copied += publicFiles
    }

    // 4. Summary for this locale
    console.log(`${lang}:`)
    console.log(`  rendered: ${stats.rendered} template file(s) (.mustache / .vue.mustache)`)
    console.log(`  copied:   ${stats.copied} file(s)`)
    console.log()
  }

  console.log('=== Done ===')
}

main().catch((err: unknown) => {
  console.error('Fatal error:', err instanceof Error ? err.message : String(err))
  process.exit(1)
})
