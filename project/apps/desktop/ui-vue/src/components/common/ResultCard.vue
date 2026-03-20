<template>
  <div class="result-card" :class="[`status-${status}`, `type-${type}`]">
    <div v-if="title" class="result-card-header">
      <span class="result-card-title">{{ title }}</span>
      <span v-if="status" class="result-card-status" :class="`badge-${statusBadge}`">
        {{ statusLabel }}
      </span>
    </div>

    <div class="result-card-body">
      <!-- text -->
      <div v-if="type === 'text'" class="result-text">
        <slot>{{ data }}</slot>
      </div>

      <!-- list -->
      <ul v-else-if="type === 'list'" class="result-list">
        <li v-for="(item, i) in dataItems" :key="i">{{ item }}</li>
      </ul>

      <!-- table -->
      <table v-else-if="type === 'table'" class="result-table">
        <thead v-if="tableHeaders.length">
          <tr>
            <th v-for="h in tableHeaders" :key="h">{{ h }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in tableRows" :key="i">
            <td v-for="(cell, j) in row" :key="j">{{ cell }}</td>
          </tr>
        </tbody>
      </table>

      <!-- json fallback -->
      <div v-else-if="type === 'json'" class="result-json">
        <button class="result-json-toggle" @click="jsonExpanded = !jsonExpanded">
          {{ jsonExpanded ? '收起' : '展开' }} JSON
        </button>
        <pre v-if="jsonExpanded">{{ formattedJson }}</pre>
      </div>

      <!-- default slot -->
      <slot v-else />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  status: { type: String, default: '' }, // success, error, warning, info, running
  type: { type: String, default: 'text' }, // text, list, table, json, media
  data: { type: [String, Array, Object], default: null },
})

const jsonExpanded = ref(false)

const statusBadge = computed(() => {
  const map = { success: 'success', error: 'danger', warning: 'warn', info: 'info', running: 'info' }
  return map[props.status] || 'info'
})

const statusLabel = computed(() => {
  const map = { success: '完成', error: '失败', warning: '警告', info: '信息', running: '运行中' }
  return map[props.status] || props.status
})

const dataItems = computed(() => {
  if (Array.isArray(props.data)) return props.data
  return []
})

const tableHeaders = computed(() => {
  if (!props.data || !Array.isArray(props.data) || props.data.length === 0) return []
  const first = props.data[0]
  if (typeof first === 'object' && first !== null) return Object.keys(first)
  return []
})

const tableRows = computed(() => {
  if (!props.data || !Array.isArray(props.data)) return []
  return props.data.map(row => {
    if (typeof row === 'object' && row !== null) return Object.values(row)
    return [row]
  })
})

const formattedJson = computed(() => {
  try {
    return JSON.stringify(props.data, null, 2)
  } catch {
    return String(props.data)
  }
})
</script>

<style scoped>
.result-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 12px;
}

.result-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
}

.result-card-title {
  font-size: 14px;
  font-weight: 600;
}

.result-card-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
}

.result-card-body {
  padding: 16px;
}

.result-text {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.result-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.8;
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.result-table th,
.result-table td {
  padding: 6px 10px;
  border: 1px solid var(--border);
  text-align: left;
}

.result-table th {
  background: var(--surface2);
  font-weight: 600;
  font-size: 12px;
}

.result-json-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
  margin-bottom: 8px;
}

.result-json pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  max-height: 400px;
  overflow: auto;
  background: var(--surface2);
  padding: 12px;
  border-radius: 4px;
}

.status-success { border-left: 3px solid #34c759; }
.status-error { border-left: 3px solid #ff3b30; }
.status-warning { border-left: 3px solid #f0ad4e; }
.status-running { border-left: 3px solid var(--accent); }
</style>
