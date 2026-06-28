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
<button v-if="show" @click="scrollToTop" aria-label="Scroll to top"
  class="fixed bottom-6 right-6 z-50 w-11 h-11 min-w-[44px] min-h-[44px] rounded-full bg-blue-600 text-white shadow-lg hover:bg-blue-700 focus-visible:ring-2 focus-visible:ring-blue-400 transition-all flex items-center justify-center">
  <Icon icon="fa6-solid:arrow-up" class="text-sm" />
</button>
</template>
