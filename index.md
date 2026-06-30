---
title: FFmpeg MSVC Prebuilt
description: Prebuilt FFmpeg binaries for Windows with MSVC
---

# FFmpeg MSVC Prebuilt

Ready-to-use FFmpeg binaries for Windows, compiled with Microsoft Visual C++. All dependencies included — download, extract, and run.

Choose your language:

- [**English** — FFmpeg MSVC Prebuilt](/en/) — Prebuilt FFmpeg binaries for Windows with MSVC
- [**中文** — FFmpeg MSVC 预构建](/zh/) — 适用于 Windows 的 FFmpeg MSVC 预构建二进制文件

<script setup lang="ts">
import { onMounted } from 'vue'

onMounted(() => {
  let lang = (navigator.language || '').toLowerCase()
  if (lang.startsWith('zh')) {
    window.location.replace('./zh/')
  } else {
    window.location.replace('./en/')
  }
})
</script>
