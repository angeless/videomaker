<template>
  <div class="diagnostics-panel">
    <!-- Tab header (B4b) -->
    <div class="dp-tabs">
      <button
        class="dp-tab"
        :class="{ active: activeTab === 'diagnostics' }"
        @click="activeTab = 'diagnostics'"
      >AI 画面诊断</button>
      <button
        class="dp-tab"
        :class="{ active: activeTab === 'stream' }"
        @click="activeTab = 'stream'"
      >视频流分析</button>
    </div>

    <!-- Tab 1: Original AI Diagnostics -->
    <div v-show="activeTab === 'diagnostics'">
      <div class="dp-header">
        <button
          class="dp-run-btn"
          @click="runDiagnosis"
          :disabled="isRunning || !vlmAvailable"
          :title="!vlmAvailable ? '请先在设置中配置 VLM' : '运行 AI 诊断'"
        >
          {{ isRunning ? '分析中…' : '运行诊断' }}
        </button>
      </div>

      <div v-if="!vlmAvailable" class="dp-notice">
        VLM 未配置。请前往设置页配置视觉语言模型。
      </div>

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

      <div v-else class="dp-empty">
        {{ hasRunOnce ? 'AI 未发现画面问题' : '点击"运行诊断"开始分析' }}
      </div>
    </div>

    <!-- Tab 2: Video Stream Analysis (B4b) -->
    <div v-show="activeTab === 'stream'">
      <div class="dp-header">
        <button
          class="dp-run-btn"
          @click="runStreamAnalysis"
          :disabled="streamLoading"
        >
          {{ streamLoading ? `分析中 (${streamProgress})…` : '运行流分析' }}
        </button>
      </div>

      <!-- Narrative arc -->
      <div v-if="store.streamAnalysis?.narrative_arc" class="dp-narrative">
        <strong>叙事弧线：</strong>{{ store.streamAnalysis.narrative_arc }}
      </div>

      <!-- Issues -->
      <div v-if="streamIssues.length > 0" class="dp-list">
        <div
          v-for="(issue, i) in streamIssues"
          :key="'si-' + i"
          class="dp-item dp-warning"
        >
          <span class="dp-severity-dot"></span>
          <span class="dp-type">[{{ issue.type }}]</span>
          <span class="dp-desc">{{ issue.description }}</span>
        </div>
      </div>

      <!-- Scene summaries -->
      <div v-if="Object.keys(store.sceneSummaries || {}).length > 0" class="dp-list" style="margin-top: 8px">
        <div class="dp-section-label">场景摘要</div>
        <div
          v-for="(scene, idx) in store.sceneSummaries"
          :key="'sc-' + idx"
          class="dp-item dp-info"
        >
          <span class="dp-severity-dot"></span>
          <span class="dp-type">[场景 {{ idx }}]</span>
          <span class="dp-desc">{{ scene.summary }}</span>
          <span v-if="scene.key_objects?.length" class="dp-suggestion">
            {{ scene.key_objects.join(', ') }}
          </span>
        </div>
      </div>

      <div v-if="streamError" class="dp-error">
        流分析失败: {{ streamError }}
        <button class="dp-retry-btn" @click="clearStreamError">重试</button>
      </div>

      <div v-else-if="!streamLoading && !store.streamAnalysis" class="dp-empty">
        点击"运行流分析"开始视频流分析
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()

const activeTab = ref('diagnostics')
const diagnostics = ref([])
const isRunning = ref(false)
const vlmAvailable = ref(false)
const hasRunOnce = ref(false)
const streamLoading = ref(false)
const streamProgress = ref('0%')
const streamError = ref('')

const streamIssues = computed(() => store.streamAnalysis?.issues || [])

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
    const video = document.querySelector('.review-player video')
    let frameB64 = null
    if (video) {
      const c = document.createElement('canvas')
      c.width = video.videoWidth || 640
      c.height = video.videoHeight || 360
      c.getContext('2d').drawImage(video, 0, 0, c.width, c.height)
      frameB64 = c.toDataURL('image/jpeg', 0.85).split(',')[1]
    }
    if (!frameB64) { diagnostics.value = []; return }

    const resp = await fetch(`/api/review/${store.sessionId}/vlm/diagnose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frame_base64: frameB64 }),
    })
    const data = await resp.json()
    diagnostics.value = data.diagnostics || []
  } catch { diagnostics.value = [] }
  finally { isRunning.value = false }
}

function clearStreamError() {
  streamError.value = ''
}

async function runStreamAnalysis() {
  if (streamLoading.value || !store.sessionId) return
  streamLoading.value = true
  streamProgress.value = '0%'
  streamError.value = ''
  const MAX_POLLS = 60
  try {
    // Trigger analysis
    const triggerResp = await fetch(`/api/review/${store.sessionId}/vlm/analyze-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_path: store.session?.video_path || '' }),
    })
    if (!triggerResp.ok) {
      const errData = await triggerResp.json().catch(() => ({}))
      streamError.value = errData.message || `HTTP ${triggerResp.status}`
      return
    }
    const triggerData = await triggerResp.json()
    if (!triggerData.job_id) {
      streamError.value = '分析启动失败，服务端未返回 job_id'
      return
    }

    // Poll for results (max 2 min)
    let completed = false
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, 2000))
      try {
        const analysisResp = await fetch(`/api/review/${store.sessionId}/vlm/stream-analysis`)
        if (analysisResp.ok) {
          const analysis = await analysisResp.json()
          store.streamAnalysis = analysis
          // Also load summaries
          const sumResp = await fetch(`/api/review/${store.sessionId}/vlm/scene-summaries`)
          if (sumResp.ok) {
            const sumData = await sumResp.json()
            store.sceneSummaries = sumData.summaries || {}
          }
          completed = true
          break
        }
      } catch { /* still processing, continue polling */ }
      streamProgress.value = `${Math.min(95, (i + 1) * 5)}%`
    }
    if (!completed) {
      streamError.value = '分析超时（超过 120 秒），请重试'
    }
  } catch (e) {
    streamError.value = e?.message || '网络错误，流分析失败'
  } finally {
    streamLoading.value = false
  }
}

function seekTo(diagnostic) {
  if (diagnostic.time_start_ms != null) store.seekTo(diagnostic.time_start_ms)
}

onMounted(checkVlmStatus)
</script>

<style scoped>
.diagnostics-panel { padding: 8px 12px; }

.dp-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 8px;
  border-bottom: 1px solid #333;
}

.dp-tab {
  background: none;
  border: none;
  color: #888;
  font-size: 0.75rem;
  padding: 6px 12px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.dp-tab.active {
  color: #fff;
  border-bottom-color: #3b82f6;
}

.dp-tab:hover:not(.active) { color: #ccc; }

.dp-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
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
.dp-run-btn:hover:not(:disabled) { background: #2563eb; }
.dp-run-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.dp-notice { font-size: 0.7rem; color: #888; padding: 12px 0; text-align: center; }

.dp-list { display: flex; flex-direction: column; gap: 4px; }

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
.dp-item:hover { background: #333; }

.dp-severity-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 2px; }
.dp-info .dp-severity-dot { background: #3b82f6; }
.dp-warning .dp-severity-dot { background: #eab308; }
.dp-error .dp-severity-dot { background: #ef4444; }

.dp-type { color: #888; flex-shrink: 0; }
.dp-desc { flex: 1; }
.dp-suggestion { color: #7b8cff; font-size: 0.65rem; }

.dp-empty { font-size: 0.7rem; color: #666; padding: 16px 0; text-align: center; }

.dp-narrative {
  font-size: 0.7rem;
  color: #aaa;
  padding: 6px 8px;
  background: #1e1e2e;
  border-radius: 4px;
  margin-bottom: 8px;
}

.dp-section-label {
  font-size: 0.65rem;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 2px;
}

.dp-error {
  font-size: 0.7rem;
  color: #ef4444;
  padding: 8px;
  background: #2a1111;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dp-retry-btn {
  background: none;
  border: 1px solid #ef4444;
  color: #ef4444;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.65rem;
  cursor: pointer;
  white-space: nowrap;
}
.dp-retry-btn:hover { background: #3a1111; }
</style>
