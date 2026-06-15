import { defineConfig } from 'vitepress'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  title: 'FFmpeg MSVC Prebuilt',
  description: 'Prebuilt FFmpeg binaries for Windows with MSVC',
  srcDir: '.',
  srcExclude: ['src/**', 'scripts/**', 'locales/**', 'templates/**', 'data/**', '.vitepress/**', 'node_modules/**'],
  base: process.env.BASE_URL || '/',
  cleanUrls: false,
  lastUpdated: true,

  locales: {
    en: {
      label: 'English',
      lang: 'en-US',
      title: 'FFmpeg MSVC Prebuilt',
      description: 'Prebuilt FFmpeg binaries for Windows with MSVC',
      themeConfig: {
        nav: [
          { text: 'Home', link: '/en/' },
          { text: 'Releases', link: '/en/releases' }
        ],
      }
    },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      title: 'FFmpeg MSVC 预编译',
      description: '适用于 Windows 的 FFmpeg MSVC 预编译二进制文件',
      themeConfig: {
        nav: [
          { text: '首页', link: '/zh/' },
          { text: '发布列表', link: '/zh/releases' }
        ],
      }
    }
  },

  themeConfig: {
    search: { provider: 'local' },
    outline: {
      level: [2, 3],
      label: 'On this page'
    },
    aside: false,
  },

  vite: {
    plugins: [tailwindcss() as any],
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
