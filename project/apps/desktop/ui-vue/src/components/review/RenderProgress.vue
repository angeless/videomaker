<template>
  <div v-if="visible" class="render-progress">
    <div class="rp-header">
      <span class="rp-title">渲染进度</span>
      <button v-if="status === 'rendering'" class="rp-cancel" @click="cancelRender">取消</button>
      <button v-else class="rp-close" @click="visible = false">关闭</button>
    </div>

    <div class="rp-bar-container">
      <div class="rp-bar" :style="{ width: percent + '%' }"></div>
    </div>

    <div class="rp-info">
      <span>{{ statusLabel }}</span>
      <span v-if="status === 'rendering'">{{ segments_done }}/{{ segments_total }} 段</span>
      <span v-if="status === 'rendering'">预计剩余 {{ eta_s.toFixed(0) }}s</span>
    </div>

    <div class="rp-encoder">编码器: {{ encoder }}</div>

    <div v-if="status === 'done'" class="rp-done">
      渲染完成: {{ outputPath }}
    </div>

    <div v-if="error" class="rp-error">
      错误: {{ error }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'

const visible = ref(false)
const status = ref('idle')
const percent = ref(0)
const segments_done = ref(0)
const segments_total = ref(0)
const encoder = ref('')
const eta_s = ref(0)
const elapsed_s = ref(0)
const outputPath = ref('')
const error = ref('')
let pollTimer = null

const statusLabel = computed(() => {
  const map = { idle: '等待中', rendering: '渲染中…', done: '完成', failed: '失败', cancelled: '已取消' }
  return map[status.value] || status.value
})

async function startRender(sessionId) {
  visible.value = true
  status.value = 'rendering'
  percent.value = 0
  error.value = ''

  try {
    const resp = await fetch(`/api/review/${sessionId}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const data = await resp.json()
    if (!data.job_id) {
      status.value = 'failed'
      error.value = data.message || 'Failed to start render'
      return
    }

    // Poll progress
    pollTimer = setInterval(async () => {
      try {
        const pResp = await fetch(`/api/review/${sessionId}/render/progress`)
        const pData = await pResp.json()
        percent.value = pData.percent || 0
        segments_done.value = pData.segments_done || 0
        segments_total.value = pData.segments_total || 0
        encoder.value = pData.encoder || ''
        eta_s.value = pData.eta_s || 0
        elapsed_s.value = pData.elapsed_s || 0
        status.value = pData.status || 'rendering'

        if (pData.status === 'done') {
          outputPath.value = pData.output_path || ''
          clearInterval(pollTimer)
        } else if (pData.status === 'failed' || pData.status === 'cancelled') {
          error.value = pData.error || ''
          clearInterval(pollTimer)
        }
      } catch { /* polling error, retry next tick */ }
    }, 1500)
  } catch (e) {
    status.value = 'failed'
    error.value = e.message
  }
}

async function cancelRender() {
  const sessionId = window.__reviewStore?.sessionId
  if (!sessionId) return
  try {
    await fetch(`/api/review/${sessionId}/render/cancel`, { method: 'POST' })
    status.value = 'cancelled'
    clearInterval(pollTimer)
  } catch (e) {
    error.value = e.message
  }
}

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

defineExpose({ startRender })
</script>

<style scoped>
.render-progress {
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 12px;
  margin: 8px;
}

.rp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.rp-title { font-size: 0.8rem; color: #fff; font-weight: 600; }
.rp-cancel, .rp-close {
  background: none; border: 1px solid #555; color: #ccc;
  padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; cursor: pointer;
}
.rp-cancel:hover { border-color: #ef4444; color: #ef4444; }

.rp-bar-container {
  height: 6px; background: #333; border-radius: 3px; overflow: hidden; margin-bottom: 8px;
}
.rp-bar {
  height: 100%; background: linear-gradient(90deg, #3b82f6, #06b6d4);
  border-radius: 3px; transition: width 0.3s ease;
}

.rp-info { display: flex; gap: 12px; font-size: 0.7rem; color: #aaa; margin-bottom: 4px; }
.rp-encoder { font-size: 0.65rem; color: #666; }
.rp-done { font-size: 0.7rem; color: #10b981; margin-top: 6px; }
.rp-error { font-size: 0.7rem; color: #ef4444; margin-top: 6px; }
</style>
