<template>
  <div>
    <h3>Agent 观测</h3>

    <div class="btn-row" style="margin-bottom:16px">
      <button class="btn btn-primary btn-sm" @click="loadData" :disabled="!appStore.projectDir || loading">{{ loading ? '加载中…' : '刷新观测数据' }}</button>
      <button class="btn btn-sm" @click="exportData" :disabled="!summary || exporting">{{ exporting ? '导出中…' : '导出 JSON' }}</button>
    </div>

    <div v-if="!summary && !loading" class="form-hint">点击「刷新观测数据」加载 Agent 运行统计</div>

    <!-- 概览卡片 -->
    <div v-if="summary" class="cap-section">
      <div class="cap-subtitle">运行概览</div>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-value">{{ summary.total_runs ?? historyCount }}</div>
          <div class="stat-label">总运行次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#34c759">{{ summary.success_count ?? 0 }}</div>
          <div class="stat-label">成功</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#f87171">{{ summary.failed_count ?? 0 }}</div>
          <div class="stat-label">失败</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ formatTokens(summary.total_tokens ?? 0) }}</div>
          <div class="stat-label">Token 用量</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${{ (summary.estimated_cost_usd ?? 0).toFixed(4) }}</div>
          <div class="stat-label">预估成本</div>
        </div>
      </div>
    </div>

    <!-- Top 能力 -->
    <div v-if="summary?.top_capabilities?.length" class="cap-section">
      <div class="cap-subtitle">Top 能力模块</div>
      <div v-for="item in summary.top_capabilities" :key="item.id || item.capability_id" class="rank-item">
        <span class="rank-name">{{ item.id || item.capability_id }}</span>
        <span class="rank-count">{{ item.count }} 次</span>
      </div>
    </div>

    <!-- Top 状态 -->
    <div v-if="summary?.top_statuses?.length" class="cap-section">
      <div class="cap-subtitle">状态分布</div>
      <div v-for="item in summary.top_statuses" :key="item.id || item.status" class="rank-item">
        <span class="rank-name">{{ item.id || item.status }}</span>
        <span class="rank-count">{{ item.count }} 次</span>
      </div>
    </div>

    <!-- 最近运行 -->
    <div v-if="items.length" class="cap-section">
      <div class="cap-subtitle">最近运行 ({{ items.length }})</div>
      <div class="run-list">
        <div v-for="run in items.slice(0, 20)" :key="run.job_id" class="run-item">
          <span class="run-id">{{ (run.job_id || '').slice(0, 8) }}</span>
          <span class="run-status" :class="'st-' + (run.status || 'unknown')">{{ run.status || '—' }}</span>
          <span class="run-kind text-muted">{{ run.kind || run.task_mode || '' }}</span>
          <span v-if="run.capability_ids" class="run-caps text-muted">{{ (run.capability_ids || []).join(', ') }}</span>
          <span class="run-time text-muted">{{ run.started_at || '' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const summary = ref(null)
const items = ref([])
const historyCount = ref(0)
const loading = ref(false)
const exporting = ref(false)

function formatTokens(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

async function loadData() {
  if (!appStore.projectDir || loading.value) return
  loading.value = true
  try {
    const data = await apiStore.api('GET', '/api/agent/observability?include_items=true&limit=50')
    if (data.error) { capStore.setMessage(`观测数据加载失败：${data.error}`, 'error'); return }
    summary.value = data.summary || null
    items.value = data.items || []
    historyCount.value = data.history_count || 0
    capStore.setMessage(`已加载 ${data.window_count || 0} 条 Agent 运行记录`, 'info')
  } finally {
    loading.value = false
  }
}

async function exportData() {
  exporting.value = true
  try {
    const data = await apiStore.api('POST', '/api/agent/observability/export', { format: 'json', limit: 500 })
    if (data.error) { capStore.setMessage(`导出失败：${data.error}`, 'error'); return }
    capStore.setMessage(`已导出到 ${data.output || 'data/'}`, 'success')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.btn-row { display: flex; gap: 6px; }
.form-hint { font-size: 11px; color: var(--muted); }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
.stat-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 12px; text-align: center; }
.stat-value { font-size: 20px; font-weight: 700; color: var(--accent); }
.stat-label { font-size: 11px; color: var(--muted); margin-top: 2px; }

.rank-item { display: flex; justify-content: space-between; padding: 4px 8px; border-bottom: 1px solid var(--border); font-size: 12px; }
.rank-name { font-weight: 500; }
.rank-count { color: var(--muted); }

.run-list { max-height: 400px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; }
.run-item { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-bottom: 1px solid var(--border); font-size: 12px; }
.run-id { font-family: monospace; font-size: 11px; color: var(--muted); width: 60px; flex-shrink: 0; }
.run-status { font-size: 11px; padding: 1px 6px; border-radius: 4px; flex-shrink: 0; }
.st-done, .st-success { background: rgba(52,199,89,0.15); color: #34c759; }
.st-failed, .st-error { background: rgba(248,113,113,0.15); color: #f87171; }
.st-partial { background: rgba(240,173,78,0.15); color: #f0ad4e; }
.st-running { background: rgba(90,141,238,0.15); color: var(--accent); }
.run-kind { flex-shrink: 0; }
.run-caps { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-time { flex-shrink: 0; font-size: 11px; margin-left: auto; }
</style>
