import Mustache from 'mustache'
// Disable HTML escaping — templates are Vue/JS, not raw HTML
Mustache.escape = (v: string) => v
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

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const root = join(__dirname, '../..')
const srcDir = join(root, 'src')

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
  }
  return count
}

function processDir(
  currentDir: string,
  outDirBase: string,
  srcBase: string,
  localeData: Record<string, unknown>,
  stats: { rendered: number; copied: number },
): void {
  const entries = readdirSync(currentDir, { withFileTypes: true })

  for (const entry of entries) {
    if (entry.isDirectory() && entry.name === 'public') continue

    const srcPath = join(currentDir, entry.name)
    const relPath = relative(srcBase, srcPath)
    const outPath = join(outDirBase, relPath)

    if (entry.isDirectory()) {
      mkdirSync(outPath, { recursive: true })
      processDir(srcPath, outDirBase, srcBase, localeData, stats)
    } else if (entry.name.endsWith('.vue.mustache')) {
      const template = readFileSync(srcPath, 'utf-8')
      const rendered = Mustache.render(template, localeData, {}, { tags: ['[[', ']]'] })

      const outFile = outPath.replace(/\.vue\.mustache$/, '.vue')
      mkdirSync(dirname(outFile), { recursive: true })
      writeFileSync(outFile, rendered, 'utf-8')
      stats.rendered++
    } else if (entry.name.endsWith('.mustache')) {
      const template = readFileSync(srcPath, 'utf-8')
      const rendered = Mustache.render(template, localeData, {}, { tags: ['[[', ']]'] })

      const outFile = outPath.replace(/\.mustache$/, '.md')
      mkdirSync(dirname(outFile), { recursive: true })
      writeFileSync(outFile, rendered, 'utf-8')
      stats.rendered++
    } else {
      mkdirSync(dirname(outPath), { recursive: true })
      writeFileSync(outPath, readFileSync(srcPath))
      stats.copied++
    }
  }
}

export async function main(): Promise<void> {
  console.log('=== render-locales ===\n')

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

    if (existsSync(outDir)) {
      rmSync(outDir, { recursive: true })
    }
    mkdirSync(outDir, { recursive: true })

    const stats = { rendered: 0, copied: 0 }

    processDir(srcDir, outDir, srcDir, localeData, stats)

    const publicDir = join(srcDir, 'public')
    if (existsSync(publicDir)) {
      const publicOutDir = join(outDir, 'public')
      cpSync(publicDir, publicOutDir, { recursive: true })
      const publicFiles = countFiles(publicDir)
      stats.copied += publicFiles
    }

    // 4. Copy docs/{lang}/ into locale output
    const docsDir = join(root, 'docs', lang)
    if (existsSync(docsDir)) {
      cpSync(docsDir, outDir, { recursive: true })
      const docFiles = countFiles(docsDir)
      stats.copied += docFiles
    }

    console.log(`${lang}:`)
    console.log(`  rendered: ${stats.rendered} template file(s) (.mustache / .vue.mustache)`)
    console.log(`  copied:   ${stats.copied} file(s)`)
    console.log()
  }

  console.log('=== Done ===')
}
