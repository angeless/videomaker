<template>
  <div>
    <h3>内容发布</h3>
    <div class="cap-section">
      <div class="form-row"><label>输入模式</label>
        <select v-model="input.input_mode" class="form-input"><option value="project">项目</option><option value="inline">内联</option></select>
      </div>
      <div class="form-row"><label>标题</label><input v-model="input.title" class="form-input" /></div>
      <div class="form-row"><label>描述</label><textarea v-model="input.description" class="form-input" rows="2"></textarea></div>
      <div class="form-row"><label>关键词</label><input v-model="input.keywords" class="form-input" placeholder="逗号分隔" /></div>
      <div class="form-row"><label>媒体链接</label><input v-model="input.media_urls" class="form-input" placeholder="逗号分隔" /></div>
      <div class="form-row"><label>平台</label><input v-model="input.platforms" class="form-input" placeholder="YouTube, 抖音 (逗号分隔)" /></div>
      <div class="form-row"><label>模拟运行</label><input type="checkbox" v-model="input.dry_run" /></div>
    </div>

    <div class="btn-row" style="margin-bottom:16px">
      <button class="btn btn-sm" @click="bootstrap" :disabled="!appStore.projectDir || loadingBootstrap">{{ loadingBootstrap ? '初始化中…' : '初始化会话' }}</button>
      <button class="btn btn-sm" @click="buildPlan" :disabled="loadingPlan">{{ loadingPlan ? '生成中…' : '生成发布计划' }}</button>
      <button class="btn btn-primary btn-sm" @click="runPublish" :disabled="!publishPlan || loadingPublish">{{ loadingPublish ? '发布中…' : '执行发布' }}</button>
      <button class="btn btn-sm" @click="rerunFailed" :disabled="!publishRun || loadingRerun">{{ loadingRerun ? '复跑中…' : '复跑失败' }}</button>
    </div>

    <div v-if="session" class="cap-section">
      <div class="cap-subtitle">会话</div>
      <div class="text-muted" style="font-size:12px">ID: {{ session.session_id }}</div>
    </div>

    <div v-if="publishPlan" class="cap-section">
      <div class="cap-subtitle">发布计划 <span class="plan-badge" :class="publishPlan.dry_run ? 'badge-dry' : 'badge-live'">{{ publishPlan.dry_run ? '模拟' : '实际' }}</span></div>
      <div class="stat-row">
        <span class="stat-item">平台 <strong>{{ (publishPlan.platform_ids || []).length }}</strong></span>
        <span class="stat-item">步骤 <strong>{{ (publishPlan.steps || []).length }}</strong></span>
        <span class="stat-item">状态 <strong>{{ publishPlan.status || '—' }}</strong></span>
      </div>
      <div v-for="step in (publishPlan.steps || [])" :key="step.platform" class="step-card">
        <span class="step-platform">{{ step.platform }}</span>
        <span class="step-status" :class="'st-' + (step.status || 'planned')">{{ step.status || 'planned' }}</span>
      </div>
      <details style="margin-top:8px"><summary class="detail-summary">查看完整计划</summary><pre class="result-pre">{{ JSON.stringify(publishPlan, null, 2) }}</pre></details>
    </div>
    <div v-if="publishRun" class="cap-section">
      <div class="cap-subtitle">执行结果</div>
      <div v-if="publishRun.result" class="stat-row">
        <span class="stat-item">总数 <strong>{{ publishRun.result.summary?.total || 0 }}</strong></span>
        <span class="stat-item" style="color:#34c759">成功 <strong>{{ publishRun.result.summary?.posted || 0 }}</strong></span>
        <span v-if="publishRun.result.summary?.failed" class="stat-item" style="color:#f87171">失败 <strong>{{ publishRun.result.summary.failed }}</strong></span>
        <span v-if="publishRun.result.summary?.blocked" class="stat-item" style="color:#f0ad4e">阻塞 <strong>{{ publishRun.result.summary.blocked }}</strong></span>
      </div>
      <div v-for="step in (publishRun.result?.steps || [])" :key="step.platform" class="step-card">
        <span class="step-platform">{{ step.platform }}</span>
        <span class="step-status" :class="'st-' + (step.status || 'unknown')">{{ step.status || 'unknown' }}</span>
        <span v-if="step.error" class="step-error">{{ step.error }}</span>
        <span v-if="step.auth_hint" class="step-hint">{{ step.auth_hint }}</span>
      </div>
      <details style="margin-top:8px"><summary class="detail-summary">查看完整 JSON</summary><pre class="result-pre">{{ JSON.stringify(publishRun, null, 2) }}</pre></details>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const input = reactive({
  input_mode: 'project', title: '', description: '', keywords: '', media_urls: '',
  platforms: '', platform_content_type: 'video_post', dry_run: false, session_id: '',
  connectors_json: '{}', article_markdown: '', article_html: '',
})
const session = ref(null)
const publishPlan = ref(null)
const publishRun = ref(null)
const loadingBootstrap = ref(false)
const loadingPlan = ref(false)
const loadingPublish = ref(false)
const loadingRerun = ref(false)

function parseList(text) {
  return (text || '').replace(/\n/g, ',').replace(/，/g, ',').split(',').map(x => x.trim()).filter(Boolean)
}

async function bootstrap() {
  if (loadingBootstrap.value) return
  loadingBootstrap.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/session/bootstrap', {
      input_mode: input.input_mode, session_id: input.session_id,
    })
    if (data.error) { capStore.setMessage(`发布会话初始化失败：${data.error}`, 'error'); return }
    session.value = data.session || null
    input.session_id = session.value?.session_id || ''
    capStore.setMessage(`发布会话已初始化：${input.session_id}`, 'success')
  } finally {
    loadingBootstrap.value = false
  }
}

async function buildPlan() {
  if (loadingPlan.value) return
  loadingPlan.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/plan', {
      input_mode: input.input_mode, platforms: input.platforms,
      platform_content_type: input.platform_content_type, dry_run: input.dry_run,
      session_id: input.session_id,
      content: {
        title: input.title, description: input.description,
        keywords: parseList(input.keywords), media_urls: parseList(input.media_urls),
        article_markdown: input.article_markdown, article_html: input.article_html,
      },
    })
    if (data.error) { capStore.setMessage(`发布计划生成失败：${data.error}`, 'error'); return }
    publishPlan.value = data.plan || null
    capStore.setMessage('已生成内容发布计划', 'success')
  } finally {
    loadingPlan.value = false
  }
}

async function runPublish() {
  if (loadingPublish.value) return
  loadingPublish.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/run', {
      input_mode: input.input_mode, session_id: input.session_id,
      dry_run: input.dry_run, plan: publishPlan.value || undefined,
    })
    if (data.error) { capStore.setMessage(`内容发布执行失败：${data.error}`, 'error'); return }
    publishRun.value = data.run || null
    capStore.setMessage(`内容发布执行完成，状态：${data.state || 'unknown'}`, 'success')
  } finally {
    loadingPublish.value = false
  }
}

async function rerunFailed() {
  if (loadingRerun.value) return
  loadingRerun.value = true
  try {
    const runId = publishRun.value?.run_id
    if (!runId) { capStore.setMessage('暂无可复跑 run_id', 'warning'); return }
    const data = await apiStore.api('POST', '/api/capabilities/content_publish/rerun', {
      input_mode: input.input_mode, run_id: runId, session_id: input.session_id,
      dry_run: input.dry_run, rerun_failed_only: true,
    })
    if (data.error) { capStore.setMessage(`内容发布复跑失败：${data.error}`, 'error'); return }
    publishRun.value = data.run || publishRun.value
    capStore.setMessage(`内容发布复跑完成：${data.state || 'unknown'}`, 'success')
  } finally {
    loadingRerun.value = false
  }
}

onMounted(async () => {
  const data = await apiStore.api('GET', '/api/capabilities/content_publish/platforms')
  if (!data.error && data.platforms) { /* platforms loaded */ }
})
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 80px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 6px; flex-wrap: wrap; }
.stat-row { display: flex; flex-wrap: wrap; gap: 14px; padding: 10px 14px; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }
.stat-item { font-size: 12px; }
.stat-item strong { color: var(--accent); }
.plan-badge { font-size: 10px; padding: 1px 6px; border-radius: 4px; margin-left: 6px; }
.badge-dry { background: rgba(90,141,238,0.15); color: var(--accent); }
.badge-live { background: rgba(52,199,89,0.15); color: #34c759; }
.step-card { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }
.step-platform { font-weight: 600; min-width: 100px; }
.step-status { font-size: 11px; padding: 1px 6px; border-radius: 4px; }
.st-posted, .st-done { background: rgba(52,199,89,0.15); color: #34c759; }
.st-failed { background: rgba(248,113,113,0.15); color: #f87171; }
.st-blocked, .st-waiting_auth { background: rgba(240,173,78,0.15); color: #f0ad4e; }
.st-planned, .st-dry_run { background: rgba(90,141,238,0.15); color: var(--accent); }
.step-error { color: #f87171; font-size: 11px; }
.step-hint { color: var(--muted); font-size: 11px; font-style: italic; }
.detail-summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
</style>
