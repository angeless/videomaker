<template>
  <div class="rlp-panel">
    <div class="rlp-header" @click="expanded = !expanded">
      <span class="rlp-title">路径变更报告</span>
      <span class="rlp-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-if="expanded" class="rlp-body">
      <!-- 查询输入（硬约束 1：可操作 — 输入 uid + 查询按钮）-->
      <div class="rlp-input-row">
        <textarea
          v-model="store.relinkReportUids"
          class="form-input rlp-textarea"
          placeholder="输入素材 uid（逗号或换行分隔）..."
          rows="2"
        ></textarea>
        <button
          class="btn btn-primary rlp-btn"
          :disabled="store.relinkReportLoading"
          @click="store.fetchRelinkReport()"
        >{{ store.relinkReportLoading ? '查询中...' : '查询' }}</button>
      </div>

      <!-- 加载 / 空态 -->
      <div v-if="store.relinkReportLoading" class="rlp-loading">查询中...</div>
      <div v-else-if="store.relinkReport && store.relinkReport.length === 0" class="rlp-empty">无路径变化记录</div>

      <!-- 报告列表 -->
      <div v-else-if="store.relinkReport && store.relinkReport.length > 0" class="rlp-report">
        <div v-for="entry in store.relinkReport" :key="entry.uid" class="rlp-entry">
          <div class="rlp-entry-uid">
            <span class="rlp-uid-label">UID:</span>
            <span class="rlp-uid-value">{{ entry.uid }}</span>
            <span v-if="entry.best_path" class="rlp-best-path" :title="entry.best_path">→ {{ truncPath(entry.best_path) }}</span>
          </div>
          <div v-if="entry.changes && entry.changes.length > 0" class="rlp-changes">
            <div v-for="c in entry.changes" :key="c.change_id" class="rlp-change">
              <span class="rlp-change-type" :class="`rlp-ct-${c.change_type}`">{{ changeTypeLabel(c.change_type) }}</span>
              <span class="rlp-change-paths">
                <span class="rlp-old-path" :title="c.old_path">{{ truncPath(c.old_path) }}</span>
                <span class="rlp-arrow">→</span>
                <span class="rlp-new-path" :title="c.new_path">{{ truncPath(c.new_path) }}</span>
              </span>
              <span class="rlp-change-time">{{ c.created_at }}</span>
            </div>
          </div>
          <div v-else class="rlp-no-changes">无变化</div>
        </div>
      </div>

      <!-- 导出按钮（硬约束 1：可操作 — 复制 + 导出）-->
      <div v-if="store.relinkReport && store.relinkReport.length > 0" class="rlp-export-row">
        <button class="btn btn-ghost rlp-btn" @click="copyJson">复制 JSON</button>
        <button class="btn btn-ghost rlp-btn" @click="exportJson">导出 JSON</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useLibraryStore } from '../../stores/library.js'
import { useToastStore } from '../../stores/toast.js'

const store = useLibraryStore()
const toast = useToastStore()
const expanded = ref(false)

const changeTypeLabels = {
  relocated: '已重定位',
  added: '新增',
  unavailable: '不可用',
  primary_changed: '主路径变更',
}
function changeTypeLabel(t) { return changeTypeLabels[t] || t }

function truncPath(p) {
  if (!p) return '-'
  return p.length > 45 ? '...' + p.slice(-42) : p
}

async function copyJson() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(store.relinkReport, null, 2))
    toast.show('已复制到剪贴板', 'success')
  } catch {
    toast.show('复制失败', 'danger')
  }
}

function exportJson() {
  const blob = new Blob([JSON.stringify(store.relinkReport, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `relink-report-${Date.now()}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  toast.show('已导出 JSON', 'success')
}

watch(expanded, (val) => {
  // Lazy load: if there are uids already entered, fetch on expand
  if (val && store.relinkReportUids.trim() && !store.relinkReport) {
    store.fetchRelinkReport()
  }
})
</script>

<style scoped>
.rlp-panel {
  border: 1px solid var(--border); border-radius: 8px;
  margin-bottom: 16px; overflow: hidden;
}
.rlp-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; cursor: pointer; background: var(--surface2); user-select: none;
}
.rlp-header:hover { background: var(--surface3, rgba(255,255,255,0.06)); }
.rlp-title { font-size: 13px; font-weight: 600; }
.rlp-toggle { font-size: 12px; color: var(--muted); }
.rlp-body { padding: 10px 12px; }
.rlp-input-row { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 10px; }
.rlp-textarea { flex: 1; font-size: 12px; padding: 6px 8px; resize: vertical; min-height: 40px; }
.rlp-btn { font-size: 12px; padding: 6px 12px; }
.rlp-loading, .rlp-empty { font-size: 12px; color: var(--muted); padding: 8px 0; text-align: center; }
.rlp-report { max-height: 400px; overflow-y: auto; }
.rlp-entry {
  border: 1px solid var(--border); border-radius: 6px;
  margin-bottom: 8px; overflow: hidden;
}
.rlp-entry-uid {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; background: var(--surface2); font-size: 12px;
}
.rlp-uid-label { color: var(--muted); font-size: 10px; }
.rlp-uid-value { font-weight: 600; font-family: monospace; font-size: 11px; }
.rlp-best-path { color: #4caf50; font-size: 10px; margin-left: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rlp-changes { padding: 4px 0; }
.rlp-change {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px; font-size: 11px; border-bottom: 1px solid rgba(255,255,255,0.04);
}
.rlp-change:last-child { border-bottom: none; }
.rlp-change-type { font-size: 10px; padding: 1px 5px; border-radius: 3px; flex-shrink: 0; }
.rlp-ct-relocated { background: rgba(76,175,80,0.15); color: #4caf50; }
.rlp-ct-added { background: rgba(90,141,238,0.15); color: var(--accent); }
.rlp-ct-unavailable { background: rgba(239,83,80,0.15); color: #ef5350; }
.rlp-ct-primary_changed { background: rgba(255,183,77,0.15); color: #ffb74d; }
.rlp-change-paths { display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; overflow: hidden; }
.rlp-old-path { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rlp-arrow { color: var(--muted); flex-shrink: 0; }
.rlp-new-path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rlp-change-time { font-size: 10px; color: var(--muted); flex-shrink: 0; }
.rlp-no-changes { font-size: 11px; color: var(--muted); padding: 6px 10px; }
.rlp-export-row { display: flex; gap: 8px; margin-top: 10px; }
</style>
