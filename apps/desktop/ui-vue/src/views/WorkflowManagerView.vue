<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <ProjectTitle />
    <AppNav />
  </div>

  <div class="main">
    <div class="content" style="padding: 24px">
      <div class="section-header-row">
        <h2 class="section-title" style="margin-bottom: 0">自定义工作流管理</h2>
        <router-link to="/create/canvas" class="btn btn-ghost btn-sm">← 返回创作</router-link>
      </div>

      <!-- 模板区域 -->
      <section class="wf-section">
        <h3>可用模板</h3>
        <div v-if="loadingTemplates" class="muted-text">加载中...</div>
        <div v-else-if="templates.length === 0" class="muted-text">暂无可用模板。自定义工作流可将多个能力（选题、粗剪、配音等）串联成自动化流水线。</div>
        <div v-else class="wf-grid">
          <div v-for="tpl in templates" :key="tpl.template_id" class="card wf-template-card">
            <div class="wf-card-header">
              <strong>{{ tpl.name }}</strong>
              <span class="badge">{{ tpl.phases?.length || tpl.step_count }} 个阶段</span>
            </div>
            <p class="wf-desc">{{ tpl.description }}</p>
            <div class="wf-tags">
              <span v-for="tag in tpl.tags" :key="tag" class="tag">{{ translateTag(tag) }}</span>
            </div>
            <div class="wf-phases" v-if="tpl.phases && tpl.phases.length">
              <div v-for="phase in tpl.phases" :key="phase.phase" class="wf-phase-item">
                <span class="phase-num">{{ phase.phase }}</span>
                <span>{{ phase.name }}</span>
              </div>
            </div>
            <button
              class="btn btn-primary btn-sm"
              :disabled="instantiating === tpl.template_id"
              @click="instantiateTemplate(tpl.template_id)"
            >
              {{ instantiating === tpl.template_id ? '创建中...' : '从模板创建' }}
            </button>
          </div>
        </div>
      </section>

      <!-- 已创建工作流 -->
      <section class="wf-section" ref="myWorkflowsSection">
        <div class="wf-section-header">
          <h3>我的工作流</h3>
          <button class="btn btn-ghost btn-sm" @click="loadWorkflows">刷新</button>
        </div>
        <div v-if="loadingWorkflows" class="muted-text">加载中...</div>
        <div v-else-if="workflows.length === 0" class="muted-text">暂无自定义工作流，可从上方模板创建。</div>
        <div v-else class="wf-list">
          <div v-for="wf in workflows" :key="wf.workflow_id" :data-wf-id="wf.workflow_id" class="card wf-item-card">
            <div class="wf-card-header">
              <strong>{{ wf.name || wf.workflow_id }}</strong>
              <div class="wf-actions">
                <button
                  class="btn btn-primary btn-sm"
                  :disabled="running === wf.workflow_id"
                  @click="runWorkflow(wf.workflow_id)"
                >
                  {{ running === wf.workflow_id ? '运行中...' : '运行' }}
                </button>
                <button class="btn btn-ghost btn-sm" @click="toggleExpand(wf.workflow_id)">
                  {{ expanded === wf.workflow_id ? '收起' : '展开步骤' }}
                </button>
                <button
                  class="btn btn-danger btn-sm"
                  @click="deleteWorkflow(wf.workflow_id)"
                  :disabled="deleting === wf.workflow_id"
                >
                  {{ deleting === wf.workflow_id ? '删除中...' : '删除' }}
                </button>
              </div>
            </div>
            <p class="wf-desc" v-if="wf.description">{{ wf.description }}</p>
            <div class="wf-meta">
              <span v-if="wf.updated_at">更新: {{ formatDate(wf.updated_at) }}</span>
              <span v-if="wf.tags" class="wf-tags-inline">
                <span v-for="tag in (wf.tags || [])" :key="tag" class="tag">{{ translateTag(tag) }}</span>
              </span>
            </div>

            <!-- 展开步骤详情 -->
            <div v-if="expanded === wf.workflow_id && wf.steps" class="wf-steps">
              <div v-for="step in wf.steps" :key="step.step_id" class="wf-step-row">
                <span class="step-index">{{ step.index || '•' }}</span>
                <template v-if="editingStep === step.step_id">
                  <input
                    v-model="editStepName"
                    class="form-input step-edit-input"
                    @keyup.enter="saveStepName(wf.workflow_id, step.step_id)"
                    @keyup.escape="editingStep = ''"
                  />
                  <button class="btn btn-primary btn-xs" @click="saveStepName(wf.workflow_id, step.step_id)">保存</button>
                  <button class="btn btn-ghost btn-xs" @click="editingStep = ''">取消</button>
                </template>
                <template v-else>
                  <span class="step-name">{{ step.name }}</span>
                  <span class="step-cap muted-text">{{ capabilityLabel(step.capability_id) }}</span>
                  <button class="btn btn-ghost btn-xs step-edit-btn" @click="startEditStep(step)">编辑</button>
                </template>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 运行历史 -->
      <section class="wf-section">
        <h3>运行历史</h3>
        <div v-if="loadingRuns" class="muted-text">加载中...</div>
        <div v-else-if="runs.length === 0" class="muted-text">暂无运行记录。创建工作流后点击运行即可在此查看执行日志。</div>
        <div v-else class="wf-list">
          <div v-for="run in runs" :key="run.run_id" class="card wf-run-card">
            <div class="wf-card-header">
              <span>
                <strong>{{ resolveWorkflowName(run.workflow_id) }}</strong>
                <span class="badge" :class="'badge-' + (run.status || 'pending')">{{ runStatusLabel(run.status) }}</span>
              </span>
              <span class="muted-text">{{ formatDate(run.started_at || run.created_at) }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useApiStore } from '../stores/api.js'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import labels from '../i18n/labels.js'
import { translateTag } from '../composables/useSemanticTranslation.js'
import AppNav from '../components/layout/AppNav.vue'
import ProjectTitle from '../components/common/ProjectTitle.vue'

const api = useApiStore()
const appStore = useAppStore()
const toast = useToastStore()
const myWorkflowsSection = ref(null)

// ── 模板 ──
const templates = ref([])
const loadingTemplates = ref(false)
const instantiating = ref('')

async function loadTemplates() {
  loadingTemplates.value = true
  const data = await api.api('GET', '/api/workflows/templates')
  loadingTemplates.value = false
  if (data.error) {
    toast.show('加载模板失败: ' + (data.error || ''), 'danger')
    return
  }
  templates.value = data.templates || []
}

async function instantiateTemplate(templateId) {
  instantiating.value = templateId
  const data = await api.api('POST', `/api/workflows/templates/${templateId}/instantiate`, {})
  instantiating.value = ''
  if (data.error) {
    toast.show('创建失败: ' + (data.error || ''), 'danger')
    return
  }
  toast.show('工作流已创建: ' + (data.workflow?.name || templateId), 'success')
  await loadWorkflows()
  await nextTick()
  myWorkflowsSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── 工作流列表 ──
const workflows = ref([])
const loadingWorkflows = ref(false)
const expanded = ref('')
const deleting = ref('')
const running = ref('')
const editingStep = ref('')
const editStepName = ref('')

async function loadWorkflows() {
  loadingWorkflows.value = true
  const data = await api.api('GET', '/api/workflows?include_steps=true')
  loadingWorkflows.value = false
  if (data.error) {
    toast.show('加载工作流失败', 'danger')
    return
  }
  workflows.value = data.workflows || []
}

function toggleExpand(id) {
  const wasExpanded = expanded.value === id
  expanded.value = wasExpanded ? '' : id
  if (!wasExpanded) {
    nextTick(() => {
      const el = document.querySelector(`[data-wf-id="${id}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }
}

async function deleteWorkflow(id) {
  if (!confirm(`确定删除工作流 "${id}" 吗？此操作不可恢复。`)) return
  deleting.value = id
  const data = await api.api('DELETE', `/api/workflows/${id}`)
  deleting.value = ''
  if (data.error) {
    toast.show('删除失败: ' + (data.error || ''), 'danger')
    return
  }
  toast.show('已删除', 'success')
  await loadWorkflows()
}

function startEditStep(step) {
  editingStep.value = step.step_id
  editStepName.value = step.name || ''
}

async function saveStepName(workflowId, stepId) {
  if (!editStepName.value.trim()) return
  const data = await api.api('PATCH', `/api/workflows/${workflowId}/steps/${stepId}`, {
    name: editStepName.value.trim(),
  })
  editingStep.value = ''
  if (data.error) {
    toast.show('保存失败: ' + (data.error || ''), 'danger')
    return
  }
  toast.show('已更新', 'success')
  await loadWorkflows()
}

async function runWorkflow(id) {
  running.value = id
  const data = await api.api('POST', `/api/workflows/${id}/run`)
  running.value = ''
  if (data.error) {
    toast.show('运行失败: ' + (data.error || ''), 'danger')
    return
  }
  toast.show('工作流已启动', 'success')
  await loadRuns()
}

// ── 运行历史 ──
const runs = ref([])
const loadingRuns = ref(false)

async function loadRuns() {
  loadingRuns.value = true
  const data = await api.api('GET', '/api/workflows/runs?limit=20')
  loadingRuns.value = false
  if (data.error) return
  runs.value = data.items || []
}

// ── 工具 ──
// W-01: capability_id → 中文标签映射（补充 labels.tools.items 未覆盖的 ID）
const capIdFallback = {
  text_rough_cut: '文字粗剪',
  image_semantic: '图片语义',
  subtitle_calibration: '字幕校准',
  topic_library: '选题库',
  topic_copy: '选题文案',
  short_clip: '短视频快剪',
  refinement: '视频精剪',
  audio_voice: '配乐配音',
  article_expand: '公众号扩写',
  publish_prep: '发布文案',
  social_export: '社媒导出',
  content_publish: '内容发布',
}

function capabilityLabel(capId) {
  if (!capId) return ''
  const item = labels.tools?.items?.[capId]
  if (item?.label) return item.label
  if (capIdFallback[capId]) return capIdFallback[capId]
  // fallback: 将 snake_case 转为可读格式
  return capId.replace(/_/g, ' ')
}

function resolveWorkflowName(wfId) {
  const wf = workflows.value.find(w => w.workflow_id === wfId)
  return wf?.name || wfId
}

function runStatusLabel(status) {
  const map = { completed: '已完成', running: '运行中', failed: '失败', pending: '等待中', done: '已完成', error: '失败' }
  return map[status] || status || '未知'
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

onMounted(() => {
  loadTemplates()
  loadWorkflows()
  loadRuns()
})
</script>

<style scoped>
.section-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 20px;
}

.wf-section {
  margin-bottom: 32px;
}

.wf-section h3 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text);
}

.wf-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.wf-section-header h3 {
  margin-bottom: 0;
}

.muted-text {
  color: var(--muted);
  font-size: 13px;
}

.wf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.wf-template-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wf-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.wf-desc {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.5;
  margin: 0;
}

.wf-tags, .wf-tags-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.wf-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--muted);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  background: var(--surface2);
  color: var(--text);
}

.badge-completed, .badge-done {
  background: rgba(52, 211, 153, 0.15);
  color: var(--success);
}

.badge-error, .badge-failed {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
}

.badge-running {
  background: rgba(96, 165, 250, 0.15);
  color: var(--accent);
}

.wf-phases {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.wf-phase-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}

.phase-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--surface2);
  font-size: 10px;
  font-weight: 600;
}

.wf-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wf-item-card {
  padding: 16px;
}

.wf-actions {
  display: flex;
  gap: 6px;
}

.wf-steps {
  margin-top: 12px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.wf-step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}

.step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-name {
  flex: 1;
}

.step-cap {
  font-size: 12px;
}

.step-edit-btn {
  opacity: 0;
  transition: opacity 0.15s;
  font-size: 11px;
  padding: 1px 6px;
}

.wf-step-row:hover .step-edit-btn {
  opacity: 1;
}

.step-edit-input {
  flex: 1;
  font-size: 13px;
  padding: 3px 8px;
  max-width: 200px;
}

.btn-xs {
  font-size: 11px;
  padding: 2px 8px;
}

.wf-run-card {
  padding: 12px 16px;
}
</style>
