import { defineConfig } from 'vitepress'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import { main as generate } from '../scripts/lib/generate-content'
import { main as render } from '../scripts/lib/render-locales'

export default defineConfig({
  title: 'FFmpeg MSVC Prebuilt',
  description: 'Prebuilt FFmpeg binaries for Windows with MSVC',
  srcDir: '.',
  srcExclude: ['src/**', 'scripts/**', 'locales/**', 'templates/**', 'data/**', '.vitepress/**', 'node_modules/**'],
  base: process.env.BASE_URL || '/',
  cleanUrls: false,
  lastUpdated: true,

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    ['meta', { name: 'og:title', content: 'FFmpeg MSVC Prebuilt' }],
    ['meta', { name: 'og:description', content: 'Prebuilt FFmpeg binaries for Windows with MSVC' }],
    ['meta', { name: 'og:type', content: 'website' }],
  ],

  locales: {
    en: {
      label: 'English',
      lang: 'en-US',
      title: 'FFmpeg MSVC Prebuilt',
      description: 'Prebuilt FFmpeg binaries for Windows with MSVC',
      themeConfig: {
        nav: [
          { text: 'Home', link: '/en/' },
          { text: 'Releases', link: '/en/releases' },
          { text: 'Guide', link: '/en/guide' },
          { text: 'Integration', link: '/en/integration' },
          { text: 'Reference', link: '/en/reference' },
        ],
      }
    },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      title: 'FFmpeg MSVC 预构建',
      description: '适用于 Windows 的 FFmpeg MSVC 预构建二进制文件',
      themeConfig: {
        nav: [
          { text: '首页', link: '/zh/' },
          { text: '构建列表', link: '/zh/releases' },
          { text: '使用指南', link: '/zh/guide' },
          { text: '开发集成', link: '/zh/integration' },
          { text: '功能参考', link: '/zh/reference' },
        ],
      }
    }
  },

  themeConfig: {
    search: false,
    outline: {
      level: [2, 3],
      label: 'On this page'
    },
    aside: false,
    socialLinks: [
      { icon: 'github', link: process.env.VITE_GITHUB_REPO_URL || 'https://github.com/System233/ffmpeg-msvc-prebuilt' }
    ],
  },

  vite: {
    plugins: [
      tailwindcss() as any,
      {
        name: 'watch-templates-plugin',
        configureServer(server) {
          let generating = false
          let timer: ReturnType<typeof setTimeout> | null = null

          const rootDir = path.resolve(__dirname, '..')

          server.watcher.add([
            path.join(rootDir, 'src'),
            path.join(rootDir, 'locales'),
          ])

          server.watcher.on('change', (filePath: string) => {
            const rel = path.relative(rootDir, filePath)
            if (!rel.startsWith('src') && !rel.startsWith('locales')) return
            if (timer) clearTimeout(timer)
            timer = setTimeout(async () => {
              if (generating) return
              generating = true
              console.log(`\n[Template Changed] ${rel}\nRegenerating...`)
              try {
                generate()
                await render()
                console.log('✨ Regeneration complete!\n')
              } catch (err) {
                console.error('❌ Regeneration failed:', err)
              } finally {
                generating = false
              }
            }, 300)
          })
        },
      },
    ],
    ssr: { noExternal: [] },
    css: {
      preprocessorOptions: {
        css: {
          additionalData: `@import "tailwindcss";`
        }
      }
    }
  }
})
