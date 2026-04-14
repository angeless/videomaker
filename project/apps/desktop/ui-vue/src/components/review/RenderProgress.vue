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
      渲染完成
      <button class="rp-download-link" :disabled="downloading" @click="downloadRender">
        {{ downloading ? '下载中…' : '下载' }}
      </button>
      <span class="rp-path">{{ outputPath }}</span>
    </div>

    <div v-if="error" class="rp-error">
      错误: {{ error }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useReviewStore } from '../../stores/review.js'
import { useApiStore } from '../../stores/api.js'

const apiStore = useApiStore()

const _sessionId = ref('')

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
const downloading = ref(false)
let pollTimer = null
let _downloadAbort = null

const statusLabel = computed(() => {
  const map = { idle: '等待中', rendering: '渲染中…', done: '完成', failed: '失败', cancelled: '已取消' }
  return map[status.value] || status.value
})

async function startRender(sessionId) {
  _sessionId.value = sessionId
  visible.value = true
  status.value = 'rendering'
  percent.value = 0
  error.value = ''

  // apiStore.api attaches auth+CSRF headers and never throws
  const data = await apiStore.api('POST', `/api/review/${sessionId}/render`, {})
  if (!data || data.error || !data.job_id) {
    status.value = 'failed'
    error.value = (data && data.error) || data?.message || 'Failed to start render'
    return
  }

  // Poll progress
  pollTimer = setInterval(async () => {
    const pData = await apiStore.api('GET', `/api/review/${sessionId}/render/progress`)
    if (!pData || pData.error) return  // keep polling; transient errors are OK
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
      pollTimer = null
    } else if (pData.status === 'failed' || pData.status === 'cancelled') {
      error.value = pData.error || ''
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, 1500)
}

async function cancelRender() {
  // Never fall back to reviewStore.sessionId — the render was started against
  // a specific session captured at startRender() time. Using the current
  // reviewStore.sessionId could cancel a DIFFERENT session's render if the
  // user has navigated between sessions while this progress bar lingers.
  const sessionId = _sessionId.value
  if (!sessionId) return
  const data = await apiStore.api('POST', `/api/review/${sessionId}/render/cancel`, {})
  if (data && !data.error) {
    status.value = 'cancelled'
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  } else if (data && data.error) {
    error.value = data.error
  }
}

// Download via fetch+blob so auth headers are sent (browser <a download> can't).
async function downloadRender() {
  if (!_sessionId.value || downloading.value) return
  downloading.value = true
  // AbortController lets us cancel a 2GB in-flight blob read on unmount/close.
  _downloadAbort = new AbortController()
  try {
    const headers = {}
    if (apiStore.token) headers['X-VideoEditor-Token'] = apiStore.token
    const resp = await fetch(
      `/api/review/${_sessionId.value}/render/download`,
      { method: 'GET', headers, signal: _downloadAbort.signal },
    )
    if (!resp.ok) {
      const msg = await resp.text().catch(() => '')
      error.value = `下载失败 (HTTP ${resp.status}): ${msg.slice(0, 120)}`
      return
    }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (outputPath.value.split('/').pop()) || 'render.mp4'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    // Safari and some older WebKit builds start the download asynchronously;
    // revoking the blob URL immediately can cancel it. Delay the revoke so
    // the browser has time to commit to the download.
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (e) {
    if (e?.name !== 'AbortError') {
      error.value = `下载失败: ${e?.message || '网络错误'}`
    }
  } finally {
    _downloadAbort = null
    downloading.value = false
  }
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  // Abort any in-flight download so we don't buffer gigabytes after unmount.
  if (_downloadAbort) _downloadAbort.abort()
})

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
.rp-done { font-size: 0.7rem; color: #10b981; margin-top: 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rp-download-link {
  color: #3b82f6; text-decoration: underline; cursor: pointer;
  background: none; border: none; padding: 0; font-size: inherit;
}
.rp-download-link:disabled { opacity: 0.5; cursor: wait; }
.rp-path { color: #888; font-size: 0.65rem; word-break: break-all; }
.rp-error { font-size: 0.7rem; color: #ef4444; margin-top: 6px; }
</style>
