<template>
  <div class="transcript-editor">
    <!-- Header: stats + actions (R13) -->
    <div class="te-header">
      <div class="te-stats">
        <span class="te-stat">原始 {{ formatDuration(store.totalDurationMs) }}</span>
        <span class="te-stat">已删 {{ formatDuration(deletedDurationMs) }}</span>
        <span class="te-stat">预计 {{ formatDuration(store.estimatedDurationMs) }}</span>
        <span class="te-stat">语气词 {{ fillers.length }}</span>
        <span class="te-stat">重复 {{ retakeCount }}</span>
        <span class="te-stat">静音 {{ silenceCount }}</span>
        <span v-if="hookParagraph" class="te-stat hook-badge">Hook ¶{{ hookParagraph.idx }}</span>
      </div>
      <div class="te-actions">
        <button class="btn btn-accent btn-sm" @click="acceptAllAI" :disabled="!hasAIMarks">
          全部接受
        </button>
        <button class="btn btn-ghost btn-sm" @click="acceptFillersOnly" :disabled="!fillers.length">
          只接受语气词
        </button>
        <button class="btn btn-ghost btn-sm" @click="restoreAll" :disabled="!deletedCount">
          全部拒绝
        </button>
        <button class="btn btn-primary btn-sm" @click="submitChanges" :disabled="!hasChanges">
          提交编辑
        </button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="store.status === 'loading'" class="te-loading">
      加载转录中...
    </div>

    <!-- Empty state -->
    <div v-else-if="!paragraphs.length" class="te-empty text-muted">
      暂无转录数据。点击上方"加载转录"按钮开始分析。
    </div>

    <!-- Paragraph list (R9) -->
    <div v-else class="te-paragraphs" ref="paragraphsRef">
      <TranscriptParagraph
        v-for="p in paragraphs"
        :key="p.idx"
        :paragraph="p"
        :currentTimeMs="store.currentTimeMs"
        :fillerWordIndices="fillerIndicesForParagraph(p.idx)"
        :retakeWordIndices="retakeIndicesForParagraph(p.idx)"
        @seek="onSeek"
        @toggle="onToggle"
        @markHook="onMarkHook"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRoughcutStore } from '../../stores/roughcut.js'
import TranscriptParagraph from './TranscriptParagraph.vue'

const store = useRoughcutStore()
const paragraphsRef = ref(null)

const paragraphs = computed(() => store.paragraphs)
const activeParagraphs = computed(() => store.activeParagraphs)
const fillers = computed(() => store.fillers)
const deletedCount = computed(() => paragraphs.value.filter(p => p.is_deleted).length)

// R13: Hook detection — first non-deleted paragraph
const hookParagraph = computed(() => {
  for (const p of paragraphs.value) {
    if (!p.is_deleted && p.is_hook) return p
  }
  return null
})

// Track if user has made changes
const hasChanges = ref(false)

// R13: Extended stats
const deletedDurationMs = computed(() =>
  paragraphs.value.filter(p => p.is_deleted).reduce((sum, p) => sum + (p.end_ms - p.start_ms), 0)
)
const retakeCount = computed(() =>
  paragraphs.value.reduce((sum, p) => sum + (p.retake_marks?.length || 0), 0)
)
const silenceCount = computed(() =>
  paragraphs.value.filter(p => p.is_silence).length
)
const hasAIMarks = computed(() =>
  paragraphs.value.some(p => p.ai_marked_delete || p.ai_marked_filler)
)

// R10: Build filler/retake word index sets per paragraph
function fillerIndicesForParagraph(paraIdx) {
  const indices = new Set()
  for (const f of fillers.value) {
    if (f.paragraph_idx === paraIdx) {
      for (const wi of (f.word_indices || [])) indices.add(wi)
    }
  }
  return indices
}

function retakeIndicesForParagraph(paraIdx) {
  // Retake marks are stored on the paragraph itself
  const p = paragraphs.value.find(p => p.idx === paraIdx)
  if (!p) return new Set()
  const indices = new Set()
  // retake_marks may come from bad_take_detector
  for (const rm of (p.retake_marks || [])) {
    for (const wi of (rm.word_indices || [])) indices.add(wi)
  }
  return indices
}

// R11: Click-to-seek
function onSeek(ms) {
  store.seekTo(ms)
}

// R12: Toggle paragraph delete/restore
function onToggle(idx) {
  store.toggleParagraph(idx)
  hasChanges.value = true
}

// R13: Batch actions
function acceptAllAI() {
  for (const p of paragraphs.value) {
    if ((p.ai_marked_delete || p.ai_marked_filler) && !p.is_deleted) {
      store.toggleParagraph(p.idx)
    }
  }
  store.batchRemoveFillers()
  hasChanges.value = true
}

function acceptFillersOnly() {
  store.batchRemoveFillers()
  hasChanges.value = true
}

// R13: Mark paragraph as hook (copied to beginning)
function onMarkHook(idx) {
  store.markHook(idx)
  hasChanges.value = true
}

function restoreAll() {
  for (const p of paragraphs.value) {
    if (p.is_deleted) store.restoreParagraph(p.idx)
  }
  hasChanges.value = true
}

async function submitChanges() {
  const operations = paragraphs.value.map(p => ({
    type: p.is_deleted ? 'delete' : 'keep',
    paragraph_idx: p.idx,
  }))
  await store.submitEdits(operations)
  hasChanges.value = false
}

// Auto-scroll to active paragraph during playback
watch(() => store.currentTimeMs, async (ms) => {
  if (!paragraphsRef.value) return
  const activeIdx = paragraphs.value.findIndex(p => ms >= p.start_ms && ms < p.end_ms)
  if (activeIdx < 0) return
  await nextTick()
  const el = paragraphsRef.value?.children?.[activeIdx]
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
})

function formatDuration(ms) {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.transcript-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-panel, #1a1a2e);
  border-radius: 8px;
  overflow: hidden;
}

.te-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
  flex-shrink: 0;
}
.te-stats { display: flex; gap: 12px; font-size: 12px; color: var(--text-muted, #9ca3af); }
.te-stat { white-space: nowrap; }
.hook-badge { color: #f59e0b; font-weight: 600; }
.te-actions { display: flex; gap: 6px; }

.te-loading, .te-empty {
  padding: 40px;
  text-align: center;
  font-size: 14px;
}

.te-paragraphs {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}
</style>
