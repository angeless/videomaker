import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useToastStore = defineStore('toast', () => {
  const toasts = ref([])

  function show(message, type = 'info', durationMs = 4000) {
    const id = Date.now() + Math.random()
    toasts.value.push({ id, message, type })
    if (durationMs > 0) {
      setTimeout(() => dismiss(id), durationMs)
    }
  }

  function dismiss(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function clearAll() {
    toasts.value = []
  }

  return { toasts, show, dismiss, clearAll }
})
