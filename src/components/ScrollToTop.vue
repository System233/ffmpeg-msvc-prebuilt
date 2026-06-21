<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Icon } from '@iconify/vue'

const show = ref(false)
let handler: (() => void) | null = null

onMounted(() => {
  handler = () => { show.value = window.scrollY > 400 }
  window.addEventListener('scroll', handler)
})
onUnmounted(() => {
  if (handler) window.removeEventListener('scroll', handler)
})

function scrollToTop() {
  if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' })
}
</script>

<template>
<button v-if="show" @click="scrollToTop"
  class="fixed bottom-6 right-6 z-50 w-10 h-10 rounded-full bg-blue-600 text-white shadow-lg hover:bg-blue-700 transition-all flex items-center justify-center">
  <Icon icon="fa6-solid:arrow-up" class="text-sm" />
</button>
</template>
