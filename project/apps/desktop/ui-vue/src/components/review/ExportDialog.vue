<script setup>
/**
 * ExportDialog.vue — R21: Comment export dialog (JSON/CSV/EDL).
 */
import { ref } from 'vue'
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()

const emit = defineEmits(['close'])

const format = ref('json')
const exporting = ref(false)
const exported = ref(false)
const exportData = ref('')

const formats = [
  { value: 'json', label: 'JSON', desc: '完整评论数据' },
  { value: 'csv', label: 'CSV', desc: '时间码/类型/文本/状态' },
  { value: 'edl', label: 'EDL', desc: 'CMX 3600 (Premiere/DaVinci)' },
]

async function doExport() {
  exporting.value = true
  try {
    const resp = await store._fetch(
      'GET',
      `/api/review/${store.sessionId}/comments/export?format=${format.value}`,
    )
    if (resp && resp.data) {
      exportData.value = typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data, null, 2)
      exported.value = true
    }
  } finally {
    exporting.value = false
  }
}

function copyToClipboard() {
  navigator.clipboard.writeText(exportData.value)
}
</script>

<template>
  <div class="export-dialog-overlay" @click.self="emit('close')">
    <div class="export-dialog">
      <div class="dialog-header">
        <h3>导出评论</h3>
        <button class="btn-close" @click="emit('close')">×</button>
      </div>

      <div v-if="!exported" class="dialog-body">
        <div class="format-options">
          <label
            v-for="f in formats" :key="f.value"
            class="format-option" :class="{ selected: format === f.value }"
          >
            <input type="radio" v-model="format" :value="f.value">
            <div>
              <strong>{{ f.label }}</strong>
              <span class="format-desc">{{ f.desc }}</span>
            </div>
          </label>
        </div>

        <button class="btn btn-primary" :disabled="exporting" @click="doExport">
          {{ exporting ? '导出中…' : '导出' }}
        </button>
      </div>

      <div v-else class="dialog-body">
        <div class="export-preview">
          <pre>{{ exportData.slice(0, 500) }}{{ exportData.length > 500 ? '...' : '' }}</pre>
        </div>
        <div class="export-actions">
          <button class="btn btn-ghost" @click="copyToClipboard">复制到剪贴板</button>
          <button class="btn btn-ghost" @click="exported = false">重新选择格式</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.export-dialog-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.export-dialog {
  background: var(--bg-panel, #1e293b); border-radius: 8px;
  width: 420px; max-height: 80vh; overflow-y: auto;
  border: 1px solid var(--border, #334155);
}
.dialog-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--border, #334155);
}
.dialog-header h3 { margin: 0; font-size: 15px; }
.btn-close { background: none; border: none; color: var(--text); font-size: 20px; cursor: pointer; }
.dialog-body { padding: 16px; }
.format-options { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.format-option {
  display: flex; align-items: center; gap: 10px; padding: 10px;
  border: 1px solid var(--border, #334155); border-radius: 6px; cursor: pointer;
}
.format-option.selected { border-color: var(--accent, #3b82f6); }
.format-desc { display: block; font-size: 11px; color: var(--text-muted, #94a3b8); }
.export-preview {
  background: var(--bg-code, #0f172a); padding: 10px; border-radius: 4px;
  max-height: 200px; overflow-y: auto; margin-bottom: 12px;
}
.export-preview pre { font-size: 11px; margin: 0; white-space: pre-wrap; }
.export-actions { display: flex; gap: 8px; }
</style>
