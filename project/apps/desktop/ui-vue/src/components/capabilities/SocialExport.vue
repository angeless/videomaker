<template>
  <div>
    <h3>{{ L.socialExport.title }}</h3>

    <!-- 输入表单 -->
    <div class="cap-section">
      <div class="form-row"><label>{{ L.socialExport.form.inputVideo }}</label><input v-model="input.input_video" class="form-input" :placeholder="L.socialExport.form.inputVideoPlaceholder" /></div>
      <div class="form-row"><label>{{ L.socialExport.form.quality }}</label>
        <select v-model="input.quality" class="form-input">
          <option v-for="(label, val) in L.socialExport.form.qualityOptions" :key="val" :value="val">{{ label }}</option>
        </select>
      </div>
      <div class="form-row"><label>{{ L.socialExport.form.outputDir }}</label><input v-model="input.output_dir" class="form-input" :placeholder="L.socialExport.form.outputDirPlaceholder" /></div>
      <div class="form-row">
        <label class="checkbox-label">
          <input type="checkbox" v-model="input.strict_duration_limit" />
          {{ L.socialExport.form.strictDuration }}
        </label>
        <span class="text-muted" style="font-size:11px">{{ L.socialExport.form.strictDurationHint }}</span>
      </div>
    </div>

    <!-- 平台选择 toggle 卡片 -->
    <div class="cap-section">
      <div class="cap-subtitle">
        {{ L.socialExport.profiles.title }}
        <span v-if="selectedPlatforms.size" class="selection-count">{{ L.socialExport.profiles.selected }} {{ selectedPlatforms.size }} {{ L.socialExport.profiles.platforms }}</span>
      </div>
      <div v-if="!profiles.length" class="text-muted" style="font-size:12px">{{ L.common.loading }}</div>
      <div class="profile-grid">
        <div v-for="p in profiles" :key="p.platform_id"
             class="profile-card" :class="{ selected: selectedPlatforms.has(p.platform_id) }"
             @click="togglePlatform(p.platform_id)">
          <div class="card-header">
            <span class="card-check">{{ selectedPlatforms.has(p.platform_id) ? '✓' : '' }}</span>
            <strong class="card-name">{{ p.name || p.platform_id }}</strong>
          </div>
          <div class="card-specs">
            <span class="spec-item">{{ p.width }}x{{ p.height }}</span>
            <span class="spec-item">{{ p.fps }}fps</span>
            <span class="spec-item orientation">{{ p.height > p.width ? '📱' : '🖥' }} {{ p.height > p.width ? L.socialExport.profiles.portrait : L.socialExport.profiles.landscape }}</span>
          </div>
          <div class="card-meta">
            <span class="spec-item">{{ L.socialExport.profiles.maxDuration }} {{ formatDuration(p.max_duration_s) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="btn-row" style="margin-bottom:16px">
      <button class="btn btn-sm" @click="buildPlan" :disabled="!appStore.projectDir || !selectedPlatforms.size || loadingPlan">{{ loadingPlan ? L.socialExport.actions.planning : L.socialExport.actions.plan }}</button>
      <button class="btn btn-sm" @click="validate" :disabled="!appStore.projectDir || !selectedPlatforms.size || loadingValidate">{{ loadingValidate ? L.socialExport.actions.validating : L.socialExport.actions.validate }}</button>
      <button class="btn btn-primary btn-sm" @click="runExport" :disabled="!appStore.projectDir || !selectedPlatforms.size || running">
        {{ running ? `${L.socialExport.actions.exporting} ${progress}%` : L.socialExport.actions.export }}
      </button>
    </div>

    <!-- 进度条 -->
    <div v-if="running" class="cap-section">
      <div class="progress"><div class="progress-fill" :style="{ width: progress + '%' }"></div></div>
    </div>

    <!-- 导出计划 — 结构化表格 -->
    <div v-if="exportPlan" class="cap-section">
      <div class="cap-subtitle">{{ L.socialExport.plan.title }}</div>
      <table class="plan-table">
        <thead>
          <tr>
            <th>{{ L.socialExport.plan.platform }}</th>
            <th>{{ L.socialExport.plan.resolution }}</th>
            <th>{{ L.socialExport.plan.bitrate }}</th>
            <th>{{ L.socialExport.plan.status }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in (exportPlan.jobs || exportPlan.steps || [exportPlan])" :key="job.platform_id || job.platform">
            <td class="td-platform">{{ profileName(job.platform_id || job.platform) }}</td>
            <td>{{ job.width || '—' }}x{{ job.height || '—' }}</td>
            <td>{{ job.video_bitrate || '—' }}</td>
            <td><span class="plan-status" :class="'ps-' + (job.status || 'planned')">{{ job.status || 'planned' }}</span></td>
          </tr>
        </tbody>
      </table>
      <details style="margin-top:8px"><summary class="detail-summary">{{ L.contentPublish.plan.viewRaw }}</summary><pre class="result-pre">{{ JSON.stringify(exportPlan, null, 2) }}</pre></details>
    </div>

    <!-- 导出结果 — 结构化列表 -->
    <div v-if="exportResult" class="cap-section">
      <div class="cap-subtitle">{{ L.socialExport.result.title }}</div>
      <div v-if="exportResult.summary || exportResult.success !== undefined" class="stat-row">
        <span class="stat-item stat-success">{{ L.socialExport.result.success }} <strong>{{ exportResult.summary?.success || exportResult.success || 0 }}</strong></span>
        <span class="stat-item stat-fail">{{ L.socialExport.result.failed }} <strong>{{ exportResult.summary?.failed || exportResult.failed || 0 }}</strong></span>
        <span class="stat-item">{{ L.socialExport.result.total }} <strong>{{ exportResult.summary?.total || (exportResult.success || 0) + (exportResult.failed || 0) }}</strong></span>
      </div>
      <div v-for="item in (exportResult.outputs || exportResult.results || [])" :key="item.platform_id || item.platform" class="result-row">
        <span class="result-icon">{{ item.status === 'done' || item.success ? '✅' : '❌' }}</span>
        <span class="result-platform">{{ profileName(item.platform_id || item.platform) }}</span>
        <span v-if="item.output_path" class="result-path text-muted">{{ item.output_path }}</span>
        <span v-if="item.file_size_human || item.file_size" class="result-size">{{ item.file_size_human || formatBytes(item.file_size) }}</span>
        <span v-if="item.error" class="result-error">{{ item.error }}</span>
      </div>
      <details style="margin-top:8px"><summary class="detail-summary">{{ L.contentPublish.result.viewRaw }}</summary><pre class="result-pre">{{ JSON.stringify(exportResult, null, 2) }}</pre></details>
    </div>

    <!-- 历史记录 -->
    <div v-if="history.length" class="cap-section">
      <div class="cap-subtitle">{{ L.socialExport.history.title }} ({{ history.length }})</div>
      <div v-for="h in history" :key="h.batch_id" class="history-card">
        <div class="history-header">
          <span class="history-id">{{ h.batch_id?.slice(0, 12) || '—' }}</span>
          <span class="history-badge" :class="h.status === 'done' ? 'hb-success' : 'hb-warning'">{{ h.status === 'done' ? L.socialExport.result.success : h.status }}</span>
          <span v-if="h.created_at" class="text-muted" style="font-size:11px">{{ h.created_at }}</span>
          <span v-if="h.platform_count || h.platforms" class="text-muted" style="font-size:11px">{{ h.platform_count || (h.platforms || []).length }} {{ L.socialExport.profiles.platforms }}</span>
          <button v-if="h.status !== 'done'" class="btn btn-xs" @click="rerun(h.batch_id)" style="margin-left:auto">{{ L.socialExport.history.rerun }}</button>
        </div>
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
import { labels as L } from '../../i18n/labels.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()
const { waitForJob } = useJobPoller()

// --- State ---
const input = reactive({ input_video: '', quality: 'high', output_dir: '', strict_duration_limit: false })
const selectedPlatforms = reactive(new Set())
const profiles = ref([])
const exportPlan = ref(null)
const exportResult = ref(null)
const history = ref([])
const running = ref(false)
const progress = ref(0)
const loadingPlan = ref(false)
const loadingValidate = ref(false)

// --- Helpers ---
const profileNameMap = {}
function profileName(id) {
  return profileNameMap[id] || id
}
function togglePlatform(id) {
  if (selectedPlatforms.has(id)) selectedPlatforms.delete(id)
  else selectedPlatforms.add(id)
}
function selectedPlatformsStr() {
  return [...selectedPlatforms].join(',')
}
function formatDuration(seconds) {
  if (!seconds) return '—'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}min`
  return `${Math.floor(seconds / 3600)}h`
}
function formatBytes(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1048576).toFixed(1)}MB`
}

// --- API ---
async function loadProfiles() {
  const data = await apiStore.api('GET', '/api/capabilities/social_export/profiles')
  if (!data.error) {
    profiles.value = data.profiles || []
    for (const p of profiles.value) {
      profileNameMap[p.platform_id] = p.name || p.platform_id
    }
  }
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
      input_video: input.input_video, platforms: selectedPlatformsStr(), quality: input.quality,
      output_dir: input.output_dir, strict_duration_limit: input.strict_duration_limit,
    })
    if (data.error) { capStore.setMessage(`${L.socialExport.plan.title}: ${data.error}`, 'error'); return }
    exportPlan.value = data.plan || null
    capStore.setMessage(L.socialExport.plan.title + ' ' + L.common.success, 'success')
  } finally {
    loadingPlan.value = false
  }
}

async function validate() {
  if (loadingValidate.value) return
  loadingValidate.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/social_export/validate_source', {
      input_video: input.input_video, platforms: selectedPlatformsStr(), strict_duration_limit: input.strict_duration_limit,
    })
    if (data.error) { capStore.setMessage(`${L.socialExport.actions.validate}: ${data.error}`, 'error'); return }
    const s = data.report?.summary || {}
    capStore.setMessage(`${L.socialExport.actions.validate}: ${s.total_platforms || 0} ${L.socialExport.profiles.platforms}`, 'success')
  } finally {
    loadingValidate.value = false
  }
}

async function runExport() {
  if (running.value) return
  running.value = true; progress.value = 0; exportResult.value = null
  const data = await apiStore.api('POST', '/api/capabilities/social_export/run', {
    input_video: input.input_video, platforms: selectedPlatformsStr(), quality: input.quality,
    output_dir: input.output_dir, strict_duration_limit: input.strict_duration_limit,
  })
  if (data.error) { running.value = false; capStore.setMessage(`${L.socialExport.actions.export}: ${data.error}`, 'error'); return }
  capStore.setMessage(L.socialExport.actions.export + '…', 'info')
  const job = await waitForJob(data.job_id, j => { progress.value = j.progress || 0 }, 3 * 60 * 60 * 1000)
  running.value = false
  if (job.status === 'error') { capStore.setMessage(`${L.socialExport.actions.export}: ${job.error}`, 'error'); return }
  if (job.status === 'cancelled') { capStore.setMessage(L.socialExport.actions.export + ': ' + L.common.cancel, 'warning'); return }
  const r = job.result?.result || job.result || {}
  exportResult.value = r
  if (job.result?.plan) exportPlan.value = job.result.plan
  capStore.setMessage(`${L.socialExport.result.title}: ${L.socialExport.result.success} ${r.success || 0}, ${L.socialExport.result.failed} ${r.failed || 0}`, 'success')
  await loadHistory()
}

async function rerun(batchId) {
  if (running.value) return
  running.value = true; progress.value = 0; exportResult.value = null
  const data = await apiStore.api('POST', '/api/capabilities/social_export/rerun', { batch_id: batchId })
  if (data.error) { running.value = false; capStore.setMessage(`${L.socialExport.history.rerun}: ${data.error}`, 'error'); return }
  const job = await waitForJob(data.job_id, j => { progress.value = j.progress || 0 }, 3 * 60 * 60 * 1000)
  running.value = false
  if (job.status === 'error') { capStore.setMessage(`${L.socialExport.history.rerun}: ${job.error}`, 'error'); return }
  const r = job.result?.result || job.result || {}
  exportResult.value = r
  capStore.setMessage(`${L.socialExport.history.rerun}: ${L.socialExport.result.success} ${r.success || 0}`, 'success')
  await loadHistory()
}

// --- Init ---
onMounted(() => { loadProfiles(); loadHistory() })
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 80px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; width: auto; }
.checkbox-label input[type="checkbox"] { width: 14px; height: 14px; accent-color: var(--accent); }
.btn-row { display: flex; gap: 6px; flex-wrap: wrap; }
.btn-xs { font-size: 11px; padding: 2px 8px; }
.selection-count { font-size: 11px; font-weight: 400; color: var(--accent); }

/* Profile toggle cards */
.profile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.profile-card {
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px;
  cursor: pointer; font-size: 12px; transition: all 0.15s;
  background: var(--surface2);
}
.profile-card:hover { border-color: var(--accent); }
.profile-card.selected { border-color: var(--accent); background: rgba(90,141,238,0.1); }
.card-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.card-check { width: 16px; height: 16px; font-size: 12px; color: var(--accent); font-weight: 700; text-align: center; }
.card-name { font-size: 12px; }
.card-specs { display: flex; gap: 8px; flex-wrap: wrap; }
.card-meta { margin-top: 2px; }
.spec-item { font-size: 11px; color: var(--muted); }
.orientation { font-size: 10px; }

/* Plan table */
.plan-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.plan-table th { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); font-size: 11px; color: var(--muted); font-weight: 600; }
.plan-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
.td-platform { font-weight: 600; }
.plan-status { font-size: 11px; padding: 1px 6px; border-radius: 4px; }
.ps-planned { background: rgba(90,141,238,0.15); color: var(--accent); }
.ps-ready { background: rgba(52,199,89,0.15); color: #34c759; }
.ps-blocked { background: rgba(240,173,78,0.15); color: #f0ad4e; }

/* Result list */
.stat-row { display: flex; flex-wrap: wrap; gap: 14px; padding: 10px 14px; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }
.stat-item { font-size: 12px; }
.stat-item strong { color: var(--accent); }
.stat-success strong { color: #34c759; }
.stat-fail strong { color: #f87171; }
.result-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }
.result-icon { font-size: 14px; flex-shrink: 0; }
.result-platform { font-weight: 600; min-width: 100px; }
.result-path { font-size: 11px; word-break: break-all; }
.result-size { font-size: 11px; color: var(--muted); white-space: nowrap; }
.result-error { color: #f87171; font-size: 11px; }

/* History */
.history-card { padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 6px; }
.history-header { display: flex; align-items: center; gap: 8px; font-size: 12px; flex-wrap: wrap; }
.history-id { font-family: monospace; font-size: 11px; color: var(--muted); }
.history-badge { font-size: 10px; padding: 1px 6px; border-radius: 4px; }
.hb-success { background: rgba(52,199,89,0.15); color: #34c759; }
.hb-warning { background: rgba(240,173,78,0.15); color: #f0ad4e; }

/* Misc */
.detail-summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
.progress { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); transition: width 0.3s; }
</style>
