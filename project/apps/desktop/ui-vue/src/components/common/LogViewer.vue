<template>
  <div ref="logContainer" class="log-viewer" @scroll="onScroll">
    <div v-for="(line, i) in lines" :key="i" class="log-line" :class="lineClass(line)">
      {{ line }}
    </div>
    <div v-if="lines.length === 0" class="log-line" style="color: var(--muted)">暂无日志</div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  lines: { type: Array, default: () => [] },
  autoScroll: { type: Boolean, default: true },
})

const logContainer = ref(null)
const userScrolledUp = ref(false)

function lineClass(line) {
  if (!line) return ''
  const lower = `${line}`.toLowerCase()
  if (lower.includes('error') || lower.includes('失败') || lower.includes('exception')) return 'error'
  if (lower.includes('warn') || lower.includes('警告')) return 'warn'
  if (lower.includes('完成') || lower.includes('success') || lower.includes('done')) return 'success'
  return ''
}

function onScroll() {
  if (!logContainer.value) return
  const el = logContainer.value
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
  userScrolledUp.value = !atBottom
}

function scrollToBottom() {
  if (!logContainer.value || userScrolledUp.value) return
  nextTick(() => {
    const el = logContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(() => props.lines.length, () => {
  if (props.autoScroll) scrollToBottom()
})

defineExpose({ scrollToBottom })
</script>
