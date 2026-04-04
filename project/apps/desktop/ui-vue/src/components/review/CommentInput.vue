<template>
  <div class="comment-input" v-if="store.mode === 'comment'">
    <div class="ci-header">
      <span class="ci-time">{{ formatTime(store.currentTimeMs) }}</span>
      <button class="ci-close" @click="cancel" title="Esc">✕</button>
    </div>

    <!-- Type selector (1-7 hotkeys) -->
    <div class="ci-types">
      <button
        v-for="ct in COMMENT_TYPES"
        :key="ct.type"
        class="ci-type-btn"
        :class="{ active: selectedType === ct.type }"
        :style="{ '--type-color': ct.color }"
        @click="selectedType = ct.type"
        :title="ct.label + ' (' + ct.key + ')'"
      >
        <span class="ci-type-icon">{{ ct.icon }}</span>
        <span class="ci-type-label">{{ ct.label }}</span>
      </button>
    </div>

    <!-- Time range (optional) -->
    <div class="ci-range">
      <label class="ci-range-label">
        <input type="checkbox" v-model="hasRange" />
        时间范围
      </label>
      <template v-if="hasRange">
        <input
          type="number"
          v-model.number="rangeEndMs"
          class="ci-range-input"
          placeholder="结束时间(ms)"
          min="0"
        />
      </template>
    </div>

    <!-- R7 (v0.17.0): AI description prefill from VLM -->
    <div v-if="aiHint || aiHintLoading" class="ci-ai-hint">
      <span v-if="aiHintLoading" class="ci-ai-spinner">分析画面中…</span>
      <template v-else>
        <span class="ci-ai-label">AI:</span>
        <span class="ci-ai-text">{{ aiHint }}</span>
        <button class="ci-ai-dismiss" @click="dismissAiHint" title="关闭">✕</button>
      </template>
    </div>

    <!-- Text input -->
    <textarea
      ref="textareaRef"
      v-model="text"
      class="ci-textarea"
      placeholder="输入评审意见… (Cmd+Enter 提交)"
      rows="3"
      @keydown.meta.enter.prevent="submit"
      @keydown.esc="cancel"
    ></textarea>

    <!-- Submit -->
    <div class="ci-actions">
      <button class="ci-btn ci-btn-cancel" @click="cancel">取消</button>
      <button class="ci-btn ci-btn-submit" @click="submit" :disabled="!canSubmit">
        提交评审
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useReviewStore } from '../../stores/review.js'
import { COMMENT_TYPES } from '../../config/shortcuts.js'

const store = useReviewStore()
const emit = defineEmits(['submitted', 'cancelled'])

const textareaRef = ref(null)
const selectedType = ref('general')
const text = ref('')
const hasRange = ref(false)
const rangeEndMs = ref(0)

// R7 (v0.17.0): AI hint from VLM analysis
const aiHint = ref('')
const aiHintLoading = ref(false)
const visualContext = ref(null) // stored VLM analysis result

const canSubmit = computed(() => text.value.trim().length > 0 && selectedType.value)

// Auto-focus textarea when entering comment mode
watch(() => store.mode, (mode) => {
  if (mode === 'comment') {
    rangeEndMs.value = store.currentTimeMs + 3000 // default 3s range
    nextTick(() => textareaRef.value?.focus())
  }
})

// Keyboard shortcuts for type selection (1-7)
function selectTypeByKey(key) {
  const ct = COMMENT_TYPES.find(c => c.key === key)
  if (ct) selectedType.value = ct.type
}

// R7: Set AI hint from VLM analysis (called by parent via expose)
async function setAiHint(description) {
  if (description && description.summary && description.summary !== '[画面区域]') {
    aiHint.value = description.summary
    visualContext.value = description
  }
}

function setAiHintLoading(loading) {
  aiHintLoading.value = loading
}

function dismissAiHint() {
  aiHint.value = ''
  visualContext.value = null
}

async function submit() {
  if (!canSubmit.value) return
  try {
    await store.addComment({
      timeStartMs: store.currentTimeMs,
      timeEndMs: hasRange.value ? rangeEndMs.value : null,
      commentType: selectedType.value,
      text: text.value.trim(),
      drawingData: store.drawingData,
      visualContext: visualContext.value ? JSON.stringify(visualContext.value) : null,
    })
    text.value = ''
    selectedType.value = 'general'
    hasRange.value = false
    store.drawingData = null
    store.exitMode()
    emit('submitted')
  } catch (e) {
    // Error is captured by store.errorMessage
  }
}

function cancel() {
  text.value = ''
  store.exitMode()
  emit('cancelled')
}

function formatTime(ms) {
  if (!ms) return '0:00'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m + ':' + String(sec).padStart(2, '0')
}

defineExpose({ selectTypeByKey, setAiHint, setAiHintLoading, dismissAiHint })
</script>

<style scoped>
.comment-input {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 12px;
  width: 320px;
}

.ci-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.ci-time {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 0.75rem;
  color: #888;
}

.ci-close {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 2px 4px;
}

.ci-close:hover {
  color: #fff;
}

.ci-types {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.ci-type-btn {
  display: flex;
  align-items: center;
  gap: 2px;
  background: #2a2a2a;
  border: 1px solid #444;
  color: #ccc;
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.7rem;
  transition: border-color 0.15s;
}

.ci-type-btn:hover {
  border-color: var(--type-color);
}

.ci-type-btn.active {
  border-color: var(--type-color);
  background: color-mix(in srgb, var(--type-color) 15%, #2a2a2a);
}

.ci-type-icon {
  font-size: 0.75rem;
}

.ci-type-label {
  font-size: 0.65rem;
}

.ci-range {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 0.7rem;
  color: #aaa;
}

.ci-range-label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.ci-range-input {
  width: 80px;
  background: #2a2a2a;
  border: 1px solid #444;
  color: #ccc;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.7rem;
}

.ci-ai-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  margin-bottom: 6px;
  background: #2a2a3a;
  border: 1px solid #4a4a6a;
  border-radius: 4px;
  font-size: 0.7rem;
  color: #aab;
}

.ci-ai-label {
  color: #7b8cff;
  font-weight: 600;
  flex-shrink: 0;
}

.ci-ai-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ci-ai-dismiss {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  padding: 0 2px;
  font-size: 0.7rem;
  flex-shrink: 0;
}

.ci-ai-dismiss:hover {
  color: #fff;
}

.ci-ai-spinner {
  color: #7b8cff;
  font-style: italic;
}

.ci-textarea {
  width: 100%;
  background: #2a2a2a;
  border: 1px solid #444;
  color: #eee;
  padding: 8px;
  border-radius: 4px;
  font-size: 0.8rem;
  resize: vertical;
  font-family: inherit;
  margin-bottom: 8px;
}

.ci-textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

.ci-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.ci-btn {
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  font-size: 0.75rem;
  cursor: pointer;
}

.ci-btn-cancel {
  background: #333;
  color: #aaa;
}

.ci-btn-cancel:hover {
  background: #444;
}

.ci-btn-submit {
  background: #3b82f6;
  color: #fff;
}

.ci-btn-submit:hover {
  background: #2563eb;
}

.ci-btn-submit:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
