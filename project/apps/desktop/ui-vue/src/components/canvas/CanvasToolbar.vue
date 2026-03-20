<template>
  <div class="canvas-toolbar">
    <div class="toolbar-left">
      <input
        v-model="canvas.workflowName"
        class="toolbar-name-input"
        placeholder="工作流名称"
        @input="canvas.dirty = true"
      />
      <span v-if="canvas.dirty" class="toolbar-dirty">未保存</span>
      <span class="toolbar-stats">{{ canvas.nodeCount }} 个节点 · {{ canvas.edgeCount }} 条连接</span>
    </div>
    <div class="toolbar-right">
      <button class="btn btn-ghost btn-sm" :disabled="!canvas.canUndo" @click="canvas.undo()" title="撤销 (Ctrl+Z)">↩</button>
      <button class="btn btn-ghost btn-sm" :disabled="!canvas.canRedo" @click="canvas.redo()" title="重做 (Ctrl+Shift+Z)">↪</button>
      <button class="btn btn-ghost btn-sm" @click="canvas.resetView()">适应</button>
      <button class="btn btn-ghost btn-sm" @click="confirmClear">清空</button>
      <button
        v-if="canvas.workflowId"
        class="btn btn-ghost btn-sm btn-danger-text"
        @click="confirmDelete"
      >删除</button>
      <button
        class="btn btn-ghost btn-sm"
        :disabled="canvas.nodeCount === 0 || planLoading"
        @click="previewPlan"
        title="预览执行计划"
      >{{ planLoading ? '检查中…' : '预览' }}</button>
      <button
        class="btn btn-ghost btn-sm"
        :disabled="!canvas.workflowId"
        @click="loadHistory"
        title="执行历史"
      >历史</button>
      <button
        class="btn btn-primary btn-sm"
        :disabled="canvas.saving || canvas.nodeCount === 0"
        @click="canvas.saveToBackend()"
      >
        {{ canvas.saving ? '保存中...' : '保存' }}
      </button>
      <button
        class="btn btn-success btn-sm"
        :disabled="canvas.running || !canvas.workflowId"
        @click="canvas.runWorkflow()"
      >
        {{ canvas.running ? '运行中...' : '运行' }}
      </button>
    </div>
    <!-- Plan Preview Overlay -->
    <Teleport to="body">
      <div v-if="showPlan" class="overlay-backdrop" @click="showPlan = false">
        <div class="overlay-panel" @click.stop>
          <div class="overlay-header">
            <span>执行计划预览</span>
            <button class="overlay-close" @click="showPlan = false">&times;</button>
          </div>
          <div v-if="planData" class="overlay-body">
            <div v-if="planData.graph" class="plan-grid">
              <div class="plan-stat">节点 <strong>{{ planData.graph.nodes?.length || 0 }}</strong></div>
              <div class="plan-stat">边 <strong>{{ planData.graph.edges?.length || 0 }}</strong></div>
              <div class="plan-stat" :class="planData.graph.has_cycle ? 'stat-warn' : 'stat-ok'">
                循环 <strong>{{ planData.graph.has_cycle ? '有' : '无' }}</strong>
              </div>
              <div v-if="planData.graph.unreached_nodes?.length" class="plan-stat stat-warn">
                不可达 <strong>{{ planData.graph.unreached_nodes.length }}</strong>
              </div>
            </div>
            <div v-if="planData.graph?.nodes" class="plan-nodes">
              <div v-for="n in planData.graph.nodes" :key="n.step_id" class="plan-node-item">
                <span class="pn-type" :class="n.node_type === 'condition' ? 'pn-cond' : ''">{{ n.node_type === 'condition' ? '❓' : '▶' }}</span>
                <span class="pn-name">{{ n.name || n.step_id }}</span>
                <span class="pn-cap text-muted">{{ n.capability_id || '' }}</span>
              </div>
            </div>
            <div v-if="planData.warnings?.length" class="plan-warnings">
              <div v-for="(w, i) in planData.warnings" :key="i" class="plan-warn-line">⚠ {{ w }}</div>
            </div>
          </div>
          <div v-else class="overlay-body text-muted">加载中…</div>
        </div>
      </div>
    </Teleport>

    <!-- History Overlay -->
    <Teleport to="body">
      <div v-if="showHistory" class="overlay-backdrop" @click="showHistory = false">
        <div class="overlay-panel" @click.stop>
          <div class="overlay-header">
            <span>执行历史</span>
            <button class="overlay-close" @click="showHistory = false">&times;</button>
          </div>
          <div class="overlay-body">
            <div v-if="historyLoading" class="text-muted">加载中…</div>
            <div v-else-if="!historyRuns.length" class="text-muted">暂无执行记录</div>
            <div v-for="run in historyRuns" :key="run.run_id" class="history-item">
              <div class="hist-top">
                <span class="hist-id">{{ run.run_id }}</span>
                <span class="hist-status" :class="'hs-' + (run.summary?.status || run.status || 'unknown')">{{ run.summary?.status || run.status || '—' }}</span>
                <span class="hist-time text-muted">{{ run.requested_at || run.created_at || '' }}</span>
              </div>
              <div v-if="run.summary" class="hist-stats">
                <span>步骤 {{ run.summary.traversed_steps || 0 }}</span>
                <span v-if="run.summary.failed_steps">· 失败 {{ run.summary.failed_steps }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'
import { useApiStore } from '../../stores/api.js'

const canvas = useCanvasStore()
const apiStore = useApiStore()

// Plan preview
const showPlan = ref(false)
const planData = ref(null)
const planLoading = ref(false)

async function previewPlan() {
  if (canvas.nodeCount === 0) return
  planLoading.value = true
  showPlan.value = true
  planData.value = null
  try {
    const payload = { name: canvas.workflowName, steps: canvas.toSteps() }
    const data = await apiStore.api('POST', '/api/workflows/plan', payload)
    planData.value = data.error ? { warnings: [data.error] } : (data.plan || data)
  } catch (e) {
    planData.value = { warnings: [String(e)] }
  } finally {
    planLoading.value = false
  }
}

// History
const showHistory = ref(false)
const historyRuns = ref([])
const historyLoading = ref(false)

async function loadHistory() {
  if (!canvas.workflowId) return
  showHistory.value = true
  historyLoading.value = true
  historyRuns.value = []
  try {
    const data = await apiStore.api('GET', `/api/workflows/runs?workflow_id=${canvas.workflowId}`)
    historyRuns.value = Array.isArray(data.runs) ? data.runs : (Array.isArray(data) ? data : [])
  } catch { /* silent */ }
  historyLoading.value = false
}

function confirmClear() {
  if (canvas.nodeCount === 0) return
  if (confirm('确定清空画布？所有节点和连接将被移除。')) {
    canvas.clear()
  }
}

async function confirmDelete() {
  if (!canvas.workflowId) return
  if (!confirm(`确定删除工作流「${canvas.workflowName}」？此操作不可撤销。`)) return
  await canvas.deleteFromBackend()
}
</script>

<style scoped>
.canvas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--surface, #1a1a2e);
  border-bottom: 1px solid var(--border, #333);
  flex-shrink: 0;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.toolbar-name-input {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
  padding: 4px 8px;
  width: 200px;
  outline: none;
  transition: border-color 0.15s;
}

.toolbar-name-input:hover,
.toolbar-name-input:focus {
  border-color: var(--border, #333);
}

.toolbar-dirty {
  font-size: 10px;
  color: var(--warn, #fbbf24);
  background: rgba(251, 191, 36, 0.1);
  padding: 1px 6px;
  border-radius: 3px;
}

.toolbar-stats {
  font-size: 11px;
  color: var(--muted, #888);
}

.toolbar-right {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.btn-danger-text { color: var(--danger, #f87171); }
.btn-danger-text:hover { background: rgba(248, 113, 113, 0.1); }

/* Overlay */
.overlay-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 9000; display: flex; align-items: center; justify-content: center; }
.overlay-panel { background: var(--bg, #111); border: 1px solid var(--border, #333); border-radius: 12px; width: 480px; max-height: 70vh; display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,0.5); }
.overlay-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border, #333); font-size: 14px; font-weight: 600; }
.overlay-close { background: none; border: none; color: var(--muted); font-size: 20px; cursor: pointer; }
.overlay-body { padding: 16px; overflow-y: auto; font-size: 12px; }

/* Plan */
.plan-grid { display: flex; gap: 16px; margin-bottom: 12px; padding: 10px; background: var(--surface2, #1a1a2e); border-radius: 8px; }
.plan-stat { font-size: 12px; }
.plan-stat strong { color: var(--accent, #5a8dee); }
.stat-warn strong { color: var(--danger, #f87171); }
.stat-ok strong { color: #34c759; }
.plan-nodes { margin-bottom: 10px; }
.plan-node-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--border, #333); }
.pn-type { width: 20px; text-align: center; }
.pn-cond { color: var(--warning, #f0ad4e); }
.pn-name { font-weight: 500; }
.pn-cap { font-size: 11px; }
.plan-warnings { margin-top: 8px; }
.plan-warn-line { color: var(--warning, #f0ad4e); font-size: 11px; padding: 2px 0; }

/* History */
.history-item { padding: 8px 0; border-bottom: 1px solid var(--border, #333); }
.hist-top { display: flex; align-items: center; gap: 8px; }
.hist-id { font-family: monospace; font-size: 11px; }
.hist-status { font-size: 10px; padding: 1px 6px; border-radius: 4px; }
.hs-done { background: rgba(52,199,89,0.15); color: #34c759; }
.hs-partial { background: rgba(240,173,78,0.15); color: #f0ad4e; }
.hs-failed { background: rgba(248,113,113,0.15); color: #f87171; }
.hist-time { font-size: 10px; margin-left: auto; }
.hist-stats { font-size: 11px; color: var(--muted); margin-top: 2px; }
</style>
