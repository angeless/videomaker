<template>
  <div
    class="transcript-para"
    :class="{
      deleted: paragraph.is_deleted,
      active: isActive,
      hook: paragraph.is_hook,
    }"
    @click="$emit('seek', paragraph.start_ms)"
  >
    <!-- Speaker + timestamp -->
    <div class="para-header">
      <span v-if="paragraph.speaker" class="para-speaker">{{ paragraph.speaker }}</span>
      <span class="para-time text-muted">{{ formatTime(paragraph.start_ms) }}</span>
      <div class="para-actions">
        <button
          class="btn btn-ghost btn-xs"
          :title="paragraph.is_deleted ? '恢复' : '删除'"
          @click.stop="$emit('toggle', paragraph.idx)"
        >
          {{ paragraph.is_deleted ? '↩' : '✕' }}
        </button>
      </div>
    </div>

    <!-- Words with filler/retake markup (R10) -->
    <div class="para-text">
      <span
        v-for="(word, wi) in paragraph.words"
        :key="wi"
        class="word"
        :class="wordClass(wi)"
        :title="wordTitle(wi)"
        @click.stop="$emit('seek', word.start_ms)"
      >{{ word.text }}</span>
    </div>

    <!-- Marks summary -->
    <div v-if="marksSummary" class="para-marks text-muted">
      {{ marksSummary }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  paragraph: { type: Object, required: true },
  currentTimeMs: { type: Number, default: 0 },
  fillerWordIndices: { type: Set, default: () => new Set() },
  retakeWordIndices: { type: Set, default: () => new Set() },
})

defineEmits(['seek', 'toggle'])

const isActive = computed(() => {
  const t = props.currentTimeMs
  return t >= props.paragraph.start_ms && t < props.paragraph.end_ms
})

function formatTime(ms) {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

function wordClass(wi) {
  const classes = []
  if (props.fillerWordIndices.has(wi)) classes.push('filler')
  if (props.retakeWordIndices.has(wi)) classes.push('retake')
  // Highlight word at current playback time
  const word = props.paragraph.words[wi]
  if (word && props.currentTimeMs >= word.start_ms && props.currentTimeMs < word.end_ms) {
    classes.push('current')
  }
  return classes
}

function wordTitle(wi) {
  if (props.fillerWordIndices.has(wi)) return '语气词'
  if (props.retakeWordIndices.has(wi)) return '重复片段'
  return ''
}

const marksSummary = computed(() => {
  const parts = []
  if (props.fillerWordIndices.size) parts.push(`${props.fillerWordIndices.size} 语气词`)
  if (props.retakeWordIndices.size) parts.push(`${props.retakeWordIndices.size} 重复`)
  if (props.paragraph.is_hook) parts.push('Hook')
  return parts.join(' · ')
})
</script>

<style scoped>
.transcript-para {
  padding: 8px 12px;
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.transcript-para:hover { background: var(--bg-hover, rgba(255,255,255,0.04)); }
.transcript-para.active { border-left-color: var(--accent, #3b82f6); background: rgba(59,130,246,0.08); }
.transcript-para.deleted { opacity: 0.4; text-decoration: line-through; }
.transcript-para.hook { border-left-color: #f59e0b; }

.para-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}
.para-speaker { font-weight: 600; color: var(--text-primary, #e5e7eb); }
.para-actions { margin-left: auto; }

.para-text { font-size: 14px; line-height: 1.6; }
.word { cursor: pointer; padding: 0 1px; border-radius: 2px; }
.word:hover { background: rgba(255,255,255,0.1); }
.word.filler { background: rgba(239,68,68,0.2); color: #fca5a5; }
.word.retake { background: rgba(245,158,11,0.2); color: #fcd34d; }
.word.current { background: rgba(59,130,246,0.3); border-radius: 2px; }

.para-marks { font-size: 11px; margin-top: 4px; }
</style>
