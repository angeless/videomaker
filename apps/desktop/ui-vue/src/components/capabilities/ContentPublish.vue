<template>
  <div>
    <h3>{{ L.contentPublish.title }}</h3>

    <!-- 内容表单 -->
    <div class="cap-section">
      <div class="form-row"><label>{{ L.contentPublish.form.title }}</label><input v-model="input.title" class="form-input" /></div>
      <div class="form-row"><label>{{ L.contentPublish.form.description }}</label><textarea v-model="input.description" class="form-input" rows="2"></textarea></div>
      <div class="form-row"><label>{{ L.contentPublish.form.keywords }}</label><input v-model="input.keywords" class="form-input" :placeholder="L.contentPublish.form.keywordsPlaceholder" /></div>
      <div class="form-row"><label>{{ L.contentPublish.form.mediaUrls }}</label><input v-model="input.media_urls" class="form-input" :placeholder="L.contentPublish.form.mediaUrlsPlaceholder" /></div>
      <div v-if="contentType === 'article'" class="form-row"><label>{{ L.contentPublish.form.articleMarkdown }}</label><textarea v-model="input.article_markdown" class="form-input" rows="4"></textarea></div>
    </div>

    <!-- 平台选择 checkbox picker -->
    <div class="cap-section">
      <div class="cap-subtitle">{{ L.contentPublish.form.selectPlatforms }}</div>
      <div v-if="!platforms.length" class="text-muted" style="font-size:12px">{{ L.common.loading }}</div>
      <template v-for="groupKey in ['domestic', 'global', 'custom']" :key="groupKey">
        <div v-if="platformsByGroup[groupKey]?.length" class="platform-group">
          <div class="platform-group-label">{{ L.contentPublish.platformGroups[groupKey] }}</div>
          <div class="platform-grid">
            <label
              v-for="p in platformsByGroup[groupKey]" :key="p.platform_id"
              class="platform-chip"
              :class="{ selected: selectedPlatforms.has(p.platform_id), 'chip-not-ready': p.connector_ready === false }"
              :title="p.connector_ready === false ? p.setup_hint : ''"
            >
              <input type="checkbox" :checked="selectedPlatforms.has(p.platform_id)" @change="togglePlatform(p.platform_id)" />
              <span class="chip-name">{{ p.name }}</span>
              <span v-if="p.connector_ready === false" class="chip-warn">⚠️</span>
              <span v-if="p.connector_ready === true" class="chip-ok">✓</span>
              <span v-if="p.notes" class="chip-note">{{ p.notes }}</span>
            </label>
          </div>
        </div>
      </template>
    </div>

    <!-- 高级选项折叠 -->
    <details class="cap-section advanced-section">
      <summary class="detail-summary">{{ L.contentPublish.advanced.toggle }}</summary>
      <div class="form-row" style="margin-top:8px">
        <label class="checkbox-label">
          <input type="checkbox" v-model="input.dry_run" />
          {{ L.contentPublish.advanced.dryRun }}
        </label>
      </div>
    </details>

    <!-- 操作按钮 -->
    <div class="btn-row" style="margin-bottom:16px">
      <button class="btn btn-sm" @click="buildPlan" :disabled="!selectedPlatforms.size || loadingPlan">{{ loadingPlan ? L.contentPublish.actions.planning : L.contentPublish.actions.plan }}</button>
      <button class="btn btn-primary btn-sm" @click="runPublish" :disabled="!publishPlan || loadingPublish">{{ loadingPublish ? L.contentPublish.actions.publishing : L.contentPublish.actions.publish }}</button>
      <button v-if="hasFailedSteps" class="btn btn-sm" @click="rerunFailed" :disabled="loadingRerun">{{ loadingRerun ? L.contentPublish.actions.rerunning : L.contentPublish.actions.rerunFailed }}</button>
    </div>

    <!-- 发布计划结果 -->
    <div v-if="publishPlan" class="cap-section">
      <div class="cap-subtitle">{{ L.contentPublish.plan.title }} <span class="plan-badge" :class="publishPlan.dry_run ? 'badge-dry' : 'badge-live'">{{ publishPlan.dry_run ? L.contentPublish.plan.badgeDry : L.contentPublish.plan.badgeLive }}</span></div>
      <div class="stat-row">
        <span class="stat-item">{{ L.contentPublish.plan.platforms }} <strong>{{ (publishPlan.platform_ids || []).length }}</strong></span>
        <span class="stat-item">{{ L.contentPublish.plan.steps }} <strong>{{ (publishPlan.steps || []).length }}</strong></span>
        <span class="stat-item">{{ L.contentPublish.plan.status }} <strong>{{ L.contentPublish.status[publishPlan.status] || publishPlan.status || '---' }}</strong></span>
      </div>
      <div v-for="step in (publishPlan.steps || [])" :key="step.platform" class="step-card">
        <span class="step-icon">{{ L.contentPublish.statusIcon[step.status] || L.contentPublish.statusIcon.planned }}</span>
        <span class="step-platform">{{ platformName(step.platform) }}</span>
        <span class="step-status" :class="'st-' + (step.status || 'planned')">{{ L.contentPublish.status[step.status] || step.status || L.contentPublish.status.planned }}</span>
        <span v-if="step.status === 'blocked'" class="step-hint">{{ L.contentPublish.blockedReason }}</span>
      </div>
      <details style="margin-top:8px"><summary class="detail-summary">{{ L.contentPublish.plan.viewRaw }}</summary><pre class="result-pre">{{ JSON.stringify(publishPlan, null, 2) }}</pre></details>
    </div>

    <!-- 执行结果 -->
    <div v-if="publishRun" class="cap-section">
      <div class="cap-subtitle">{{ L.contentPublish.result.title }}</div>
      <div v-if="publishRun.result" class="stat-row">
        <span class="stat-item">{{ L.contentPublish.result.total }} <strong>{{ publishRun.result.summary?.total || 0 }}</strong></span>
        <span class="stat-item stat-success">{{ L.contentPublish.result.posted }} <strong>{{ publishRun.result.summary?.posted || 0 }}</strong></span>
        <span v-if="publishRun.result.summary?.failed" class="stat-item stat-fail">{{ L.contentPublish.result.failed }} <strong>{{ publishRun.result.summary.failed }}</strong></span>
        <span v-if="publishRun.result.summary?.blocked" class="stat-item stat-blocked">{{ L.contentPublish.result.blocked }} <strong>{{ publishRun.result.summary.blocked }}</strong></span>
      </div>
      <!-- 错误恢复面板 -->
      <div v-if="hasFailedSteps" class="recovery-panel">
        <div class="recovery-title">{{ L.contentPublish.recovery.title }}</div>
        <div v-if="errorClassSummary.length" class="recovery-errors">
          <div v-for="ec in errorClassSummary" :key="ec.errorClass" class="recovery-error-item">
            <span class="recovery-count">{{ ec.count }}</span>
            <span>{{ L.contentPublish.recovery.platformsFailed }}</span>
            <span class="recovery-class">{{ L.contentPublish.errors[ec.errorClass] || L.contentPublish.errors.unknown }}</span>
          </div>
        </div>
        <div v-if="!errorClassSummary.length && !recoveryHint" class="recovery-fallback text-muted">{{ L.contentPublish.recovery.fallback }}</div>
        <div class="recovery-actions">
          <button v-if="recoveryScope === 'failed_only'" class="btn btn-sm" @click="rerunFailed" :disabled="loadingRerun">{{ loadingRerun ? L.contentPublish.actions.rerunning : L.contentPublish.recovery.rerunFailed }}</button>
          <button v-else-if="recoveryScope === 'all'" class="btn btn-sm" @click="rerunAll" :disabled="loadingRerun">{{ loadingRerun ? L.contentPublish.actions.rerunning : L.contentPublish.recovery.rerunAll }}</button>
          <button v-else class="btn btn-sm" @click="rerunFailed" :disabled="loadingRerun">{{ loadingRerun ? L.contentPublish.actions.rerunning : L.contentPublish.recovery.genericRetry }}</button>
          <button v-if="recoveryErrorClasses.has('config_missing')" class="btn btn-sm" @click="goToSettings">{{ L.contentPublish.goToSettings }}</button>
          <button v-if="recoveryErrorClasses.has('auth_failed')" class="btn btn-sm" @click="autoBootstrap">{{ L.contentPublish.recovery.reauth }}</button>
        </div>
      </div>

      <div v-for="step in (publishRun.result?.steps || [])" :key="step.platform" class="step-card">
        <span class="step-icon">{{ L.contentPublish.statusIcon[step.status] || L.contentPublish.statusIcon.unknown }}</span>
        <span class="step-platform">{{ platformName(step.platform) }}</span>
        <span class="step-status" :class="'st-' + (step.status || 'unknown')">{{ L.contentPublish.status[step.status] || step.status }}</span>
        <span v-if="step.error" class="step-error">{{ step.error }}</span>
        <span v-if="step.error_class && L.contentPublish.errors[step.error_class]" class="step-hint">{{ L.contentPublish.errors[step.error_class] }}</span>
      </div>
      <details style="margin-top:8px"><summary class="detail-summary">{{ L.contentPublish.result.viewRaw }}</summary><pre class="result-pre">{{ JSON.stringify(publishRun, null, 2) }}</pre></details>
    </div>

    <!-- 发布历史 -->
    <div class="cap-section">
      <div class="cap-subtitle" style="display:flex;align-items:center;gap:8px">
        {{ L.contentPublish.history.title }}
        <button class="btn btn-xs" @click="loadHistory" :disabled="loadingHistory">{{ loadingHistory ? L.common.loading : L.contentPublish.history.refresh }}</button>
      </div>
      <div v-if="!history.length && !loadingHistory" class="text-muted" style="font-size:12px">{{ L.contentPublish.history.empty }}</div>
      <div v-for="run in history" :key="run.run_id" class="history-card">
        <div class="history-header">
          <span class="history-id">{{ run.run_id?.slice(0, 8) || '---' }}</span>
          <span class="step-status" :class="'st-' + (run.result?.status || run.status || 'unknown')">{{ L.contentPublish.status[run.result?.status || run.status] || run.result?.status || run.status || '---' }}</span>
          <span class="history-time text-muted">{{ run.requested_at || run.created_at || '' }}</span>
        </div>
        <div class="history-meta">
          <span v-if="run.result?.summary">
            {{ L.contentPublish.history.success }} {{ run.result.summary.posted || 0 }} / {{ L.contentPublish.history.fail }} {{ run.result.summary.failed || 0 }} / {{ L.contentPublish.history.total }} {{ run.result.summary.total || 0 }}
          </span>
          <span v-if="run.platforms || run.platform_ids" class="text-muted">
            {{ (run.platforms || run.platform_ids || []).map(id => platformName(id)).join(', ') }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import { labels as L } from '../../i18n/labels.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

// --- State ---
const input = reactive({
  title: '', description: '', keywords: '', media_urls: '',
  platform_content_type: 'video_post', dry_run: false,
  article_markdown: '', article_html: '',
})
const selectedPlatforms = reactive(new Set())
const platforms = ref([])
const platformGroups = ref({})
const session = ref(null)
const sessionId = ref('')
const publishPlan = ref(null)
const publishRun = ref(null)
const loadingPlan = ref(false)
const loadingPublish = ref(false)
const loadingRerun = ref(false)
const history = ref([])
const loadingHistory = ref(false)

// --- Computed ---
const inputMode = computed(() => appStore.projectDir ? 'project' : 'inline')
const contentType = computed(() => input.platform_content_type)
const platformsByGroup = computed(() => {
  const grouped = { domestic: [], global: [], custom: [] }
  for (const p of platforms.value) {
    const g = p.region || 'custom'
    if (grouped[g]) grouped[g].push(p)
    else grouped.custom.push(p)
  }
  return grouped
})
const hasFailedSteps = computed(() =>
  (publishRun.value?.result?.steps || []).some(s => s.status === 'failed')
)
const recoveryHint = computed(() => publishRun.value?.recovery_hint || publishRun.value?.result?.recovery_hint || null)
const recoveryScope = computed(() => recoveryHint.value?.rerun_scope || '')
const recoveryErrorClasses = computed(() => new Set(recoveryHint.value?.error_classes || []))
const errorClassSummary = computed(() => {
  const steps = publishRun.value?.result?.steps || []
  const counts = {}
  for (const s of steps) {
    if (s.status === 'failed' && s.error_class) {
      counts[s.error_class] = (counts[s.error_class] || 0) + 1
    }
  }
  return Object.entries(counts).map(([errorClass, count]) => ({ errorClass, count }))
})

// --- Helpers ---
const platformNameMap = computed(() => {
  const map = {}
  for (const p of platforms.value) map[p.platform_id] = p.name
  return map
})
function platformName(id) {
  return platformNameMap.value[id] || id
}
function togglePlatform(id) {
  if (selectedPlatforms.has(id)) selectedPlatforms.delete(id)
  else selectedPlatforms.add(id)
}
function parseList(text) {
  return (text || '').replace(/\n/g, ',').replace(/\uff0c/g, ',').split(',').map(x => x.trim()).filter(Boolean)
}
function selectedPlatformsStr() {
  return [...selectedPlatforms].join(',')
}

// --- API ---
async function autoBootstrap() {
  try {
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/session/bootstrap', {
      input_mode: inputMode.value,
    })
    if (data.error) {
      capStore.setMessage(L.contentPublish.bootstrapFailed, 'error')
      return
    }
    session.value = data.session || null
    sessionId.value = session.value?.session_id || ''
  } catch {
    capStore.setMessage(L.contentPublish.bootstrapFailed, 'error')
  }
}

async function buildPlan() {
  if (loadingPlan.value) return
  if (!selectedPlatforms.size) {
    capStore.setMessage(L.contentPublish.form.noPlatformSelected, 'warning')
    return
  }
  loadingPlan.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/plan', {
      input_mode: inputMode.value, platforms: selectedPlatformsStr(),
      platform_content_type: input.platform_content_type, dry_run: input.dry_run,
      session_id: sessionId.value,
      content: {
        title: input.title, description: input.description,
        keywords: parseList(input.keywords), media_urls: parseList(input.media_urls),
        article_markdown: input.article_markdown, article_html: input.article_html,
      },
    })
    if (data.error) { capStore.setMessage(`${L.contentPublish.result.failed}: ${data.error}`, 'error'); return }
    publishPlan.value = data.plan || null
    capStore.setMessage(L.contentPublish.plan.title + ' ' + L.common.success, 'success')
  } finally {
    loadingPlan.value = false
  }
}

async function runPublish() {
  if (loadingPublish.value) return
  loadingPublish.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/run', {
      input_mode: inputMode.value, session_id: sessionId.value,
      dry_run: input.dry_run, plan: publishPlan.value || undefined,
    })
    if (data.error) { capStore.setMessage(`${L.contentPublish.result.failed}: ${data.error}`, 'error'); return }
    publishRun.value = data.run || null
    const status = L.contentPublish.status[data.state] || data.state || ''
    capStore.setMessage(`${L.contentPublish.result.title}: ${status}`, 'success')
  } finally {
    loadingPublish.value = false
  }
}

async function rerunFailed() {
  if (loadingRerun.value) return
  loadingRerun.value = true
  try {
    const runId = publishRun.value?.run_id
    if (!runId) return
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/rerun', {
      input_mode: inputMode.value, run_id: runId, session_id: sessionId.value,
      dry_run: input.dry_run, rerun_failed_only: true,
    })
    if (data.error) { capStore.setMessage(`${L.contentPublish.result.failed}: ${data.error}`, 'error'); return }
    publishRun.value = data.run || publishRun.value
    capStore.setMessage(`${L.contentPublish.actions.rerunFailed}: ${L.common.success}`, 'success')
  } finally {
    loadingRerun.value = false
  }
}

async function rerunAll() {
  if (loadingRerun.value) return
  loadingRerun.value = true
  try {
    const runId = publishRun.value?.run_id
    if (!runId) return
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/rerun', {
      input_mode: inputMode.value, run_id: runId, session_id: sessionId.value,
      dry_run: input.dry_run, rerun_failed_only: false,
    })
    if (data.error) { capStore.setMessage(`${L.contentPublish.result.failed}: ${data.error}`, 'error'); return }
    publishRun.value = data.run || publishRun.value
    capStore.setMessage(`${L.contentPublish.recovery.rerunAll}: ${L.common.success}`, 'success')
  } finally {
    loadingRerun.value = false
  }
}

function goToSettings() {
  window.location.hash = '#/settings'
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const data = await apiStore.api('GET', '/api/capabilities/content_publish/history?limit=20')
    if (!data.error) history.value = data.runs || []
  } finally {
    loadingHistory.value = false
  }
}

// --- Init ---
onMounted(async () => {
  // Load platform list
  const data = await apiStore.api('GET', '/api/capabilities/content_publish/platforms')
  if (!data.error && data.platforms) {
    platforms.value = data.platforms
    platformGroups.value = data.groups || {}
  }
  // Auto bootstrap session (skip if already active)
  if (!session.value) await autoBootstrap()
  // Load history
  loadHistory()
})
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 80px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 6px; flex-wrap: wrap; }

/* Platform checkbox picker */
.platform-group { margin-bottom: 12px; }
.platform-group-label { font-size: 11px; font-weight: 600; color: var(--muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.platform-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.platform-chip {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--surface2);
  font-size: 12px; cursor: pointer; transition: all 0.15s;
}
.platform-chip:hover { border-color: var(--accent); }
.platform-chip.selected { border-color: var(--accent); background: rgba(90,141,238,0.1); }
.platform-chip input[type="checkbox"] { width: 14px; height: 14px; margin: 0; accent-color: var(--accent); }
.chip-name { font-weight: 500; }
.chip-warn { font-size: 12px; flex-shrink: 0; }
.chip-ok { font-size: 11px; color: #34c759; flex-shrink: 0; }
.chip-not-ready { border-style: dashed; opacity: 0.8; }
.chip-not-ready:hover .chip-warn { animation: pulse 1s infinite; }
@keyframes pulse { 50% { opacity: 0.5; } }
.chip-note { font-size: 10px; color: var(--muted); }

/* Advanced section */
.advanced-section { margin-bottom: 12px; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; }
.checkbox-label input[type="checkbox"] { width: 14px; height: 14px; accent-color: var(--accent); }

/* Stats & results */
.stat-row { display: flex; flex-wrap: wrap; gap: 14px; padding: 10px 14px; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }
.stat-item { font-size: 12px; }
.stat-item strong { color: var(--accent); }
.stat-success strong { color: #34c759; }
.stat-fail strong { color: #f87171; }
.stat-blocked strong { color: #f0ad4e; }
.plan-badge { font-size: 10px; padding: 1px 6px; border-radius: 4px; margin-left: 6px; }
.badge-dry { background: rgba(90,141,238,0.15); color: var(--accent); }
.badge-live { background: rgba(52,199,89,0.15); color: #34c759; }
.step-card { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }
.step-icon { font-size: 14px; flex-shrink: 0; }
.step-platform { font-weight: 600; min-width: 90px; }
.step-status { font-size: 11px; padding: 1px 6px; border-radius: 4px; }
.st-posted, .st-done { background: rgba(52,199,89,0.15); color: #34c759; }
.st-failed { background: rgba(248,113,113,0.15); color: #f87171; }
.st-blocked, .st-waiting_auth { background: rgba(240,173,78,0.15); color: #f0ad4e; }
.st-planned, .st-dry_run { background: rgba(90,141,238,0.15); color: var(--accent); }
.step-error { color: #f87171; font-size: 11px; }
.step-hint { color: var(--muted); font-size: 11px; font-style: italic; }
.detail-summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
.btn-xs { font-size: 11px; padding: 2px 8px; }

/* Recovery panel */
.recovery-panel { padding: 12px 14px; background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.25); border-radius: 8px; margin-bottom: 10px; }
.recovery-title { font-size: 12px; font-weight: 600; color: #f87171; margin-bottom: 6px; }
.recovery-errors { margin-bottom: 8px; }
.recovery-error-item { font-size: 12px; margin-bottom: 2px; display: flex; gap: 4px; align-items: center; }
.recovery-count { font-weight: 700; color: #f87171; min-width: 16px; }
.recovery-class { color: var(--muted); }
.recovery-fallback { font-size: 12px; margin-bottom: 8px; }
.recovery-actions { display: flex; gap: 6px; flex-wrap: wrap; }

/* History */
.history-card { padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 6px; }
.history-header { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.history-id { font-family: monospace; font-size: 11px; color: var(--muted); }
.history-time { font-size: 11px; margin-left: auto; }
.history-meta { font-size: 11px; margin-top: 4px; display: flex; gap: 12px; }
</style>
