---
title: FFmpeg MSVC Prebuilt
description: Prebuilt FFmpeg binaries for Windows
---

<script setup lang="ts">
import { onMounted } from 'vue'

onMounted(() => {
  let lang = (navigator.language || '').toLowerCase()
  if (lang.startsWith('zh')) {
    window.location.replace('/zh/')
  } else {
    window.location.replace('/en/')
  }
})
</script>

<noscript>
  <p>Please choose your language / 请选择语言:</p>
  <ul>
    <li><a href="/en/">English</a></li>
    <li><a href="/zh/">中文 (Chinese)</a></li>
  </ul>
</noscript>
