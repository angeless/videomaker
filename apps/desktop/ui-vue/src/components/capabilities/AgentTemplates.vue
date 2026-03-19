<template>
  <div>
    <h3>Agent 模板</h3>

    <div class="btn-row" style="margin-bottom:16px">
      <button class="btn btn-primary btn-sm" @click="loadTemplates" :disabled="!appStore.projectDir || loading">{{ loading ? '加载中…' : '刷新模板' }}</button>
    </div>

    <div v-if="!templates.length && !loading" class="form-hint">点击「刷新模板」加载已有 Agent 技能模板</div>

    <!-- 模板列表 -->
    <div v-if="templates.length" class="cap-section">
      <div class="cap-subtitle">模板列表 ({{ templates.length }})</div>
      <div class="tmpl-list">
        <div v-for="tmpl in templates" :key="tmpl.template_id" class="tmpl-card" :class="{ expanded: expandedId === tmpl.template_id }">
          <div class="tmpl-header" @click="toggle(tmpl.template_id)">
            <span class="tmpl-name">{{ tmpl.name || tmpl.template_id }}</span>
            <span class="tmpl-scope" :class="'scope-' + (tmpl.scope || 'project')">{{ tmpl.scope || 'project' }}</span>
            <span v-if="tmpl.capability_id" class="tmpl-cap text-muted">{{ tmpl.capability_id }}</span>
            <span class="tmpl-arrow">{{ expandedId === tmpl.template_id ? '▾' : '▸' }}</span>
          </div>
          <div v-if="expandedId === tmpl.template_id" class="tmpl-body">
            <div v-if="tmpl.description" class="tmpl-desc">{{ tmpl.description }}</div>
            <div class="tmpl-meta">
              <span v-if="tmpl.actor_id">Actor: {{ tmpl.actor_id }}</span>
              <span v-if="tmpl.base">继承: {{ tmpl.base }}</span>
            </div>
            <div v-if="tmpl.variables && Object.keys(tmpl.variables).length" class="tmpl-vars">
              <div class="var-title">变量</div>
              <div v-for="(val, key) in tmpl.variables" :key="key" class="var-row">
                <span class="var-key">{{ key }}</span>
                <span class="var-val text-muted">{{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}</span>
              </div>
            </div>
            <div class="tmpl-actions">
              <button v-if="tmpl.scope !== 'system'" class="btn btn-xs btn-danger" @click.stop="deleteTemplate(tmpl)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新建模板 -->
    <div class="cap-section">
      <div class="cap-subtitle">新建模板</div>
      <div class="form-row"><label>模板 ID</label><input v-model="newTmpl.template_id" class="form-input" placeholder="如 my_topic_flow" /></div>
      <div class="form-row"><label>名称</label><input v-model="newTmpl.name" class="form-input" /></div>
      <div class="form-row"><label>能力 ID</label><input v-model="newTmpl.capability_id" class="form-input" placeholder="如 topic_copy" /></div>
      <div class="form-row"><label>描述</label><input v-model="newTmpl.description" class="form-input" /></div>
      <div class="form-row"><label>变量 JSON</label><textarea v-model="newTmpl.variables_json" class="form-input" rows="3" placeholder='{"target_duration_s": 30}'></textarea></div>
      <button class="btn btn-primary btn-sm" @click="saveTemplate" :disabled="!newTmpl.template_id || saving">{{ saving ? '保存中…' : '保存模板' }}</button>
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

const templates = ref([])
const loading = ref(false)
const saving = ref(false)
const expandedId = ref('')

const newTmpl = reactive({
  template_id: '', name: '', capability_id: '', description: '', variables_json: '{}',
})

function toggle(id) {
  expandedId.value = expandedId.value === id ? '' : id
}

async function loadTemplates() {
  if (!appStore.projectDir || loading.value) return
  loading.value = true
  try {
    const data = await apiStore.api('GET', '/api/agent/templates?include_system=true&resolve=true')
    if (data.error) { capStore.setMessage(`模板加载失败：${data.error}`, 'error'); return }
    templates.value = data.templates || []
    capStore.setMessage(`已加载 ${templates.value.length} 个模板`, 'info')
  } finally {
    loading.value = false
  }
}

async function saveTemplate() {
  if (!newTmpl.template_id || saving.value) return
  saving.value = true
  try {
    let variables = {}
    try { variables = JSON.parse(newTmpl.variables_json || '{}') } catch { /* ignore */ }
    const data = await apiStore.api('POST', '/api/agent/templates', {
      template_id: newTmpl.template_id,
      name: newTmpl.name || newTmpl.template_id,
      capability_id: newTmpl.capability_id,
      description: newTmpl.description,
      variables,
      scope: 'project',
    })
    if (data.error) { capStore.setMessage(`模板保存失败：${data.error}`, 'error'); return }
    capStore.setMessage(`模板 ${newTmpl.template_id} 已保存`, 'success')
    newTmpl.template_id = ''; newTmpl.name = ''; newTmpl.capability_id = ''
    newTmpl.description = ''; newTmpl.variables_json = '{}'
    loadTemplates()
  } finally {
    saving.value = false
  }
}

async function deleteTemplate(tmpl) {
  const data = await apiStore.api('DELETE', `/api/agent/templates/${tmpl.template_id}?scope=${tmpl.scope || 'project'}`)
  if (data.error) { capStore.setMessage(`删除失败：${data.error}`, 'error'); return }
  capStore.setMessage(`模板 ${tmpl.template_id} 已删除`, 'success')
  loadTemplates()
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.btn-row { display: flex; gap: 6px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 80px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.form-hint { font-size: 11px; color: var(--muted); }
.btn-xs { font-size: 11px; padding: 2px 8px; }
.btn-danger { color: #f87171; border-color: #f87171; }

.tmpl-list { border: 1px solid var(--border); border-radius: 6px; }
.tmpl-card { border-bottom: 1px solid var(--border); }
.tmpl-card:last-child { border-bottom: none; }
.tmpl-header { display: flex; align-items: center; gap: 8px; padding: 8px 10px; cursor: pointer; font-size: 12px; }
.tmpl-header:hover { background: var(--surface2); }
.tmpl-name { font-weight: 600; }
.tmpl-scope { font-size: 10px; padding: 1px 5px; border-radius: 3px; }
.scope-system { background: rgba(90,141,238,0.15); color: var(--accent); }
.scope-project { background: rgba(52,199,89,0.15); color: #34c759; }
.scope-agent { background: rgba(240,173,78,0.15); color: #f0ad4e; }
.tmpl-cap { flex: 1; }
.tmpl-arrow { margin-left: auto; color: var(--muted); font-size: 10px; }
.tmpl-body { padding: 8px 16px 12px; background: var(--surface2); font-size: 12px; }
.tmpl-desc { margin-bottom: 6px; color: var(--text); }
.tmpl-meta { color: var(--muted); font-size: 11px; margin-bottom: 6px; display: flex; gap: 12px; }
.tmpl-vars { margin-bottom: 8px; }
.var-title { font-size: 11px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }
.var-row { display: flex; gap: 8px; padding: 2px 0; }
.var-key { font-family: monospace; font-size: 11px; min-width: 100px; }
.var-val { font-size: 11px; }
.tmpl-actions { margin-top: 4px; }
</style>
