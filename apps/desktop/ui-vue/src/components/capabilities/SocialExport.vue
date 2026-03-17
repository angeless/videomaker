<template>
  <div>
    <h3>社媒导出</h3>
    <div class="cap-section">
      <div class="form-row"><label>输入视频</label><input v-model="input.input_video" class="form-input" placeholder="留空默认 output/final.mp4" /></div>
      <div class="form-row"><label>目标平台</label><input v-model="input.platforms" class="form-input" placeholder="tiktok,抖音,小红书,youtube (逗号分隔)" /></div>
      <div class="form-row"><label>品质</label>
        <select v-model="input.quality" class="form-input"><option value="draft">草稿</option><option value="medium">中等</option><option value="high">高品质</option><option value="premium">最佳</option></select>
      </div>
      <div class="form-row"><label>输出目录</label><input v-model="input.output_dir" class="form-input" placeholder="留空默认" /></div>
      <div class="form-row"><label>严格时长</label><input type="checkbox" v-model="input.strict_duration_limit" /></div>
      <div class="btn-row">
        <button class="btn btn-sm" @click="buildPlan" :disabled="!appStore.projectDir || loadingPlan">{{ loadingPlan ? '生成中…' : '生成计划' }}</button>
        <button class="btn btn-sm" @click="validate" :disabled="!appStore.projectDir || loadingValidate">{{ loadingValidate ? '校验中…' : '校验规格' }}</button>
        <button class="btn btn-primary btn-sm" @click="runExport" :disabled="!appStore.projectDir || running">
          {{ running ? `导出中 ${progress}%` : '执行导出' }}
        </button>
      </div>
    </div>

    <div v-if="profiles.length" class="cap-section">
      <div class="cap-subtitle">平台规格 ({{ profiles.length }})</div>
      <div class="profile-grid">
        <div v-for="p in profiles" :key="p.platform_id" class="profile-item" @click="useProfile(p)">
          <strong>{{ p.name || p.platform_id }}</strong>
          <span class="text-muted">{{ p.width }}x{{ p.height }} {{ p.fps }}fps</span>
        </div>
      </div>
    </div>

    <div v-if="running" class="cap-section">
      <div class="progress"><div class="progress-fill" :style="{ width: progress + '%' }"></div></div>
    </div>

    <div v-if="exportPlan" class="cap-section">
      <div class="cap-subtitle">导出计划</div>
      <pre class="result-pre">{{ JSON.stringify(exportPlan, null, 2) }}</pre>
    </div>
    <div v-if="exportResult" class="cap-section">
      <div class="cap-subtitle">导出结果</div>
      <pre class="result-pre">{{ JSON.stringify(exportResult, null, 2) }}</pre>
    </div>

    <div v-if="history.length" class="cap-section">
      <div class="cap-subtitle">历史记录 ({{ history.length }})</div>
      <div v-for="h in history" :key="h.batch_id" class="history-item">
        <span>{{ h.batch_id }}</span>
        <span class="badge" :class="h.status === 'done' ? 'badge-success' : 'badge-warning'">{{ h.status }}</span>
        <button v-if="h.status !== 'done'" class="btn btn-xs" @click="rerun(h.batch_id)">复跑</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import { useJobPoller } from '../../composables/useJobPoller.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()
const { waitForJob } = useJobPoller()

const input = reactive({ input_video: '', platforms: '', quality: 'high', output_dir: '', strict_duration_limit: false })
const profiles = ref([])
const exportPlan = ref(null)
const exportResult = ref(null)
const history = ref([])
const running = ref(false)
const progress = ref(0)
const loadingPlan = ref(false)
const loadingValidate = ref(false)

function useProfile(p) {
  const cur = input.platforms.split(',').map(x => x.trim()).filter(Boolean)
  if (!cur.includes(p.platform_id)) { cur.push(p.platform_id); input.platforms = cur.join(',') }
}

async function loadProfiles() {
  const data = await apiStore.api('GET', '/api/capabilities/social_export/profiles')
  if (!data.error) profiles.value = data.profiles || []
}

async function loadHistory() {
  if (!appStore.projectDir) return
  const data = await apiStore.api('GET', '/api/capabilities/social_export/history?limit=50')
  if (!data.error) history.value = data.history || []
}

async function buildPlan() {
  if (loadingPlan.value) return
  loadingPlan.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/social_export/plan', {
      input_video: input.input_video, platforms: input.platforms, quality: input.quality,
      output_dir: input.output_dir, strict_duration_limit: input.strict_duration_limit,
    })
    if (data.error) { capStore.setMessage(`导出计划生成失败：${data.error}`, 'error'); return }
    exportPlan.value = data.plan || null
    capStore.setMessage('已生成社媒导出计划', 'success')
  } finally {
    loadingPlan.value = false
  }
}

async function validate() {
  if (loadingValidate.value) return
  loadingValidate.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/social_export/validate_source', {
      input_video: input.input_video, platforms: input.platforms, strict_duration_limit: input.strict_duration_limit,
    })
    if (data.error) { capStore.setMessage(`源视频规格校验失败：${data.error}`, 'error'); return }
    const s = data.report?.summary || {}
    capStore.setMessage(`规格校验完成：目标平台 ${s.total_platforms || 0} 个，需变换 ${s.transform_required_platforms || 0} 个`, 'success')
  } finally {
    loadingValidate.value = false
  }
}

async function runExport() {
  if (running.value) return
  running.value = true; progress.value = 0; exportResult.value = null
  const data = await apiStore.api('POST', '/api/capabilities/social_export/run', {
    input_video: input.input_video, platforms: input.platforms, quality: input.quality,
    output_dir: input.output_dir, strict_duration_limit: input.strict_duration_limit,
  })
  if (data.error) { running.value = false; capStore.setMessage(`启动导出失败：${data.error}`, 'error'); return }
  capStore.setMessage('社媒导出任务已提交', 'info')
  const job = await waitForJob(data.job_id, j => { progress.value = j.progress || 0 }, 3 * 60 * 60 * 1000)
  running.value = false
  if (job.status === 'error') { capStore.setMessage(`社媒导出失败：${job.error}`, 'error'); return }
  if (job.status === 'cancelled') { capStore.setMessage('社媒导出已取消', 'warning'); return }
  const r = job.result?.result || job.result || {}
  exportResult.value = r
  if (job.result?.plan) exportPlan.value = job.result.plan
  capStore.setMessage(`社媒导出完成：成功 ${r.success || 0}，失败 ${r.failed || 0}`, 'success')
  await loadHistory()
}

async function rerun(batchId) {
  if (running.value) return
  running.value = true; progress.value = 0; exportResult.value = null
  const data = await apiStore.api('POST', '/api/capabilities/social_export/rerun', { batch_id: batchId })
  if (data.error) { running.value = false; capStore.setMessage(`复跑失败：${data.error}`, 'error'); return }
  const job = await waitForJob(data.job_id, j => { progress.value = j.progress || 0 }, 3 * 60 * 60 * 1000)
  running.value = false
  if (job.status === 'error') { capStore.setMessage(`复跑失败：${job.error}`, 'error'); return }
  const r = job.result?.result || job.result || {}
  exportResult.value = r
  capStore.setMessage(`复跑完成：成功 ${r.success || 0}，失败 ${r.failed || 0}`, 'success')
  await loadHistory()
}

onMounted(() => { loadProfiles(); loadHistory() })
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 80px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 6px; flex-wrap: wrap; }
.btn-xs { font-size: 11px; padding: 2px 8px; }
.profile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; }
.profile-item { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; font-size: 12px; display: flex; flex-direction: column; }
.profile-item:hover { background: var(--surface2); }
.history-item { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 4px 0; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
</style>
