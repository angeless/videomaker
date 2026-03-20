<template>
  <div v-if="canvasStore.selectedNode" class="node-config-panel">
    <div class="panel-header">
      <h3 class="panel-title">{{ canvasStore.selectedNode.label }}</h3>
      <button class="panel-close" @click="canvasStore.selectNode(null)">&times;</button>
    </div>

    <div class="panel-body">
      <div class="config-section">
        <label class="config-label">能力 ID</label>
        <div class="config-value">{{ canvasStore.selectedNode.capabilityId }}</div>
      </div>

      <div class="config-section">
        <label class="config-label">节点名称</label>
        <input
          v-model="canvasStore.selectedNode.label"
          class="form-input"
          @change="canvasStore.dirty = true"
        />
      </div>

      <div class="config-section">
        <label class="config-label">状态</label>
        <span class="badge" :class="statusBadgeClass">{{ statusLabel }}</span>
      </div>

      <div class="config-section">
        <label class="config-label">配置参数</label>
        <textarea
          class="form-input config-json"
          :value="configJson"
          @change="onConfigChange($event.target.value)"
          rows="6"
          placeholder="{}"
        ></textarea>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'

const canvasStore = useCanvasStore()

const configJson = computed(() => {
  if (!canvasStore.selectedNode) return '{}'
  return JSON.stringify(canvasStore.selectedNode.config || {}, null, 2)
})

const statusLabel = computed(() => {
  if (!canvasStore.selectedNode) return ''
  const s = canvasStore.nodeStatuses[canvasStore.selectedNode.id]
  const map = { pending: '等待中', running: '运行中', done: '完成', error: '失败' }
  return map[s] || '空闲'
})

const statusBadgeClass = computed(() => {
  const s = canvasStore.nodeStatuses[canvasStore.selectedNode?.id]
  const map = { pending: 'badge-warn', running: 'badge-info', done: 'badge-success', error: 'badge-danger' }
  return map[s] || 'badge-info'
})

function onConfigChange(val) {
  try {
    const parsed = JSON.parse(val)
    canvasStore.updateNodeConfig(canvasStore.selectedNode.id, parsed)
  } catch {
    // ignore parse errors while typing
  }
}
</script>

<style scoped>
.node-config-panel {
  width: 280px;
  border-left: 1px solid var(--border);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.panel-close {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
}

.panel-close:hover {
  color: var(--text);
}

.panel-body {
  padding: 16px;
}

.config-section {
  margin-bottom: 14px;
}

.config-label {
  display: block;
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.config-value {
  font-size: 13px;
  color: var(--text);
}

.config-json {
  font-family: monospace;
  font-size: 12px;
  resize: vertical;
}
</style>
