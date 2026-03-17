<template>
  <div>
    <h3>短视频快剪</h3>
    <div class="cap-section">
      <div class="form-row"><label>目标时长(秒)</label><input v-model.number="input.target_duration_s" type="number" class="form-input" /></div>
      <div class="form-row"><label>最大片段数</label><input v-model.number="input.max_clips" type="number" class="form-input" /></div>
      <button class="btn btn-primary btn-sm" @click="build" :disabled="!appStore.projectDir || loading">{{ loading ? '生成中…' : '生成快剪规划' }}</button>
    </div>
    <div v-if="plan" class="cap-section">
      <div class="cap-subtitle">快剪规划</div>
      <pre class="result-pre">{{ JSON.stringify(plan, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const input = reactive({ target_duration_s: 30, max_clips: 8 })
const plan = ref(null)
const loading = ref(false)

async function build() {
  if (!appStore.projectDir || loading.value) return
  loading.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/short_clip/plan', {
      target_duration_s: input.target_duration_s, max_clips: input.max_clips,
    })
    if (data.error) { capStore.setMessage(`快剪规划失败：${data.error}`, 'error'); return }
    plan.value = data.plan || null
    capStore.setMessage('已生成短视频快剪规划', 'success')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 100px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
</style>
