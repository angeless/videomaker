<template>
  <div class="diagnostics-panel">
    <div class="dp-header">
      <h3 class="dp-title">AI 画面诊断</h3>
      <button
        class="dp-run-btn"
        @click="runDiagnosis"
        :disabled="isRunning || !vlmAvailable"
        :title="!vlmAvailable ? '请先在设置中配置 VLM' : '运行 AI 诊断'"
      >
        {{ isRunning ? '分析中…' : '运行诊断' }}
      </button>
    </div>

    <!-- VLM unavailable notice -->
    <div v-if="!vlmAvailable" class="dp-notice">
      VLM 未配置。请前往设置页配置视觉语言模型。
    </div>

    <!-- Diagnostics list -->
    <div v-else-if="diagnostics.length > 0" class="dp-list">
      <div
        v-for="(d, i) in diagnostics"
        :key="i"
        class="dp-item"
        :class="'dp-' + d.severity"
        @click="seekTo(d)"
      >
        <span class="dp-severity-dot"></span>
        <span class="dp-type">[{{ d.issue_type }}]</span>
        <span class="dp-desc">{{ d.description }}</span>
        <span v-if="d.suggestion" class="dp-suggestion">{{ d.suggestion }}</span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="dp-empty">
      {{ hasRunOnce ? 'AI 未发现画面问题' : '点击"运行诊断"开始分析' }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()

const diagnostics = ref([])
const isRunning = ref(false)
const vlmAvailable = ref(false)
const hasRunOnce = ref(false)

async function checkVlmStatus() {
  try {
    const resp = await fetch('/api/vlm/status')
    const data = await resp.json()
    vlmAvailable.value = data.available === true
  } catch {
    vlmAvailable.value = false
  }
}

async function runDiagnosis() {
  if (isRunning.value || !store.sessionId) return
  isRunning.value = true
  hasRunOnce.value = true
  try {
    // Capture current frame
    const video = document.querySelector('.review-player video')
    let frameB64 = null
    if (video) {
      const c = document.createElement('canvas')
      c.width = video.videoWidth || 640
      c.height = video.videoHeight || 360
      c.getContext('2d').drawImage(video, 0, 0, c.width, c.height)
      frameB64 = c.toDataURL('image/jpeg', 0.85).split(',')[1]
    }

    if (!frameB64) {
      diagnostics.value = []
      return
    }

    const resp = await fetch(`/api/review/${store.sessionId}/vlm/diagnose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frame_base64: frameB64 }),
    })
    const data = await resp.json()
    diagnostics.value = data.diagnostics || []
  } catch (e) {
    diagnostics.value = []
  } finally {
    isRunning.value = false
  }
}

function seekTo(diagnostic) {
  if (diagnostic.time_start_ms != null) {
    store.seekTo(diagnostic.time_start_ms)
  }
}

onMounted(checkVlmStatus)
</script>

<style scoped>
.diagnostics-panel {
  padding: 8px 12px;
}

.dp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.dp-title {
  font-size: 0.8rem;
  color: #ccc;
  margin: 0;
}

.dp-run-btn {
  background: #3b82f6;
  color: #fff;
  border: none;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  cursor: pointer;
}

.dp-run-btn:hover:not(:disabled) {
  background: #2563eb;
}

.dp-run-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.dp-notice {
  font-size: 0.7rem;
  color: #888;
  padding: 12px 0;
  text-align: center;
}

.dp-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dp-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  background: #2a2a2a;
  cursor: pointer;
  font-size: 0.7rem;
  color: #ddd;
}

.dp-item:hover {
  background: #333;
}

.dp-severity-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 2px;
}

.dp-info .dp-severity-dot { background: #3b82f6; }
.dp-warning .dp-severity-dot { background: #eab308; }
.dp-error .dp-severity-dot { background: #ef4444; }

.dp-type {
  color: #888;
  flex-shrink: 0;
}

.dp-desc {
  flex: 1;
}

.dp-suggestion {
  color: #7b8cff;
  font-size: 0.65rem;
}

.dp-empty {
  font-size: 0.7rem;
  color: #666;
  padding: 16px 0;
  text-align: center;
}
</style>
