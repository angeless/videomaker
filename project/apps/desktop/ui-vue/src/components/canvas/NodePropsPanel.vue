<template>
  <aside v-if="node" class="node-props-panel">
    <div class="panel-header">
      <span class="panel-title">节点属性</span>
      <button class="panel-close" @click="canvas.clearSelection">&times;</button>
    </div>

    <!-- 基础信息 -->
    <div class="prop-group">
      <label>名称</label>
      <input v-model="editLabel" class="form-input" @change="saveLabel" />
    </div>

    <div class="prop-group">
      <label>节点类型</label>
      <select v-model="editNodeType" class="form-input" @change="saveNodeType">
        <option value="action">执行 (action)</option>
        <option value="condition">条件 (condition)</option>
      </select>
    </div>

    <div v-if="editNodeType === 'action'" class="prop-group">
      <label>能力</label>
      <div class="prop-value">{{ node.capability_id || '—' }}</div>
    </div>

    <!-- 条件节点额外字段 -->
    <div v-if="editNodeType === 'condition'" class="prop-group">
      <label>条件表达式</label>
      <input v-model="editCondition" class="form-input" placeholder="如 {{last.response.ok}}" @change="saveExtras" />
    </div>

    <!-- 分支路由 -->
    <div class="prop-section-title">分支路由</div>

    <div class="prop-group">
      <label>默认下一步</label>
      <select v-model="editNextStepId" class="form-input" @change="saveExtras">
        <option value="">（自动）</option>
        <option v-for="n in otherNodes" :key="n.id" :value="n.id">{{ n.label }}</option>
      </select>
    </div>

    <div class="prop-group">
      <label>成功跳转</label>
      <select v-model="editNextOnSuccess" class="form-input" @change="saveExtras">
        <option value="">（跟随默认）</option>
        <option v-for="n in otherNodes" :key="n.id" :value="n.id">{{ n.label }}</option>
      </select>
    </div>

    <div class="prop-group">
      <label>失败跳转</label>
      <select v-model="editNextOnError" class="form-input" @change="saveExtras">
        <option value="">（跟随默认）</option>
        <option v-for="n in otherNodes" :key="n.id" :value="n.id">{{ n.label }}</option>
      </select>
    </div>

    <div class="prop-group">
      <label>跳过跳转</label>
      <select v-model="editNextOnSkip" class="form-input" @change="saveExtras">
        <option value="">（跟随默认）</option>
        <option v-for="n in otherNodes" :key="n.id" :value="n.id">{{ n.label }}</option>
      </select>
    </div>

    <!-- 其他选项 -->
    <div class="prop-group">
      <label class="checkbox-label">
        <input type="checkbox" v-model="editContinueOnError" @change="saveExtras" />
        失败时继续
      </label>
    </div>

    <div class="prop-group">
      <label class="checkbox-label">
        <input type="checkbox" v-model="editEnabled" @change="saveExtras" />
        启用
      </label>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'

const canvas = useCanvasStore()

const node = computed(() => {
  if (!canvas.selectedNodeId) return null
  return canvas.nodes.find(n => n.id === canvas.selectedNodeId) || null
})

const otherNodes = computed(() => {
  if (!node.value) return []
  return canvas.nodes.filter(n => n.id !== node.value.id)
})

// Editable fields
const editLabel = ref('')
const editNodeType = ref('action')
const editCondition = ref('')
const editNextStepId = ref('')
const editNextOnSuccess = ref('')
const editNextOnError = ref('')
const editNextOnSkip = ref('')
const editContinueOnError = ref(false)
const editEnabled = ref(true)

// Sync from store → local when selection changes
watch(node, (n) => {
  if (!n) return
  editLabel.value = n.label || ''
  editNodeType.value = n.node_type || 'action'
  editCondition.value = n.condition || ''
  editNextStepId.value = n.next_step_id || ''
  editNextOnSuccess.value = n.next_on_success || ''
  editNextOnError.value = n.next_on_error || ''
  editNextOnSkip.value = n.next_on_skip || ''
  editContinueOnError.value = n.continue_on_error || false
  editEnabled.value = n.enabled !== false
}, { immediate: true })

function saveLabel() {
  if (!node.value || !editLabel.value.trim()) return
  canvas.renameNode(node.value.id, editLabel.value)
}

function saveNodeType() {
  if (!node.value) return
  canvas.updateNodeProps(node.value.id, { node_type: editNodeType.value })
}

function saveExtras() {
  if (!node.value) return
  canvas.updateNodeProps(node.value.id, {
    condition: editCondition.value,
    next_step_id: editNextStepId.value,
    next_on_success: editNextOnSuccess.value,
    next_on_error: editNextOnError.value,
    next_on_skip: editNextOnSkip.value,
    continue_on_error: editContinueOnError.value,
    enabled: editEnabled.value,
  })
}
</script>

<style scoped>
.node-props-panel {
  width: 240px;
  border-left: 1px solid var(--border, #333);
  background: var(--bg, #111);
  padding: 12px;
  overflow-y: auto;
  flex-shrink: 0;
}

.panel-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
}
.panel-title { font-size: 13px; font-weight: 600; }
.panel-close { background: none; border: none; color: var(--muted); font-size: 18px; cursor: pointer; padding: 0 4px; }

.prop-group { margin-bottom: 10px; }
.prop-group label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 3px; }
.prop-value { font-size: 12px; color: var(--text); padding: 4px 0; }
.prop-section-title { font-size: 11px; font-weight: 600; color: var(--muted); margin: 14px 0 8px; border-top: 1px solid var(--border); padding-top: 10px; }

.form-input {
  width: 100%; font-size: 12px; padding: 5px 8px;
  background: var(--surface, #1a1a2e); border: 1px solid var(--border, #333);
  border-radius: 4px; color: var(--text); outline: none;
}
.form-input:focus { border-color: var(--accent, #5a8dee); }

.checkbox-label {
  display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text); cursor: pointer;
}
</style>
