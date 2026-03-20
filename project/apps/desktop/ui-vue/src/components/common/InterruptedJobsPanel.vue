<template>
  <div v-if="system.interruptedJobs.length > 0" class="interrupted-panel">
    <div class="interrupted-header">
      <span class="interrupted-title">{{ L.interruptedJobs.panelTitle }}</span>
      <span class="interrupted-desc">{{ L.interruptedJobs.panelDesc }}</span>
    </div>

    <div class="interrupted-actions-bar">
      <button class="btn btn-primary btn-sm" :disabled="acting" @click="handleRetryAll">
        {{ acting === 'retry' ? L.interruptedJobs.retrying : L.interruptedJobs.retryAll }}
      </button>
      <button class="btn btn-ghost btn-sm" :disabled="acting" @click="handleIgnoreAll">
        {{ acting === 'ignore' ? L.interruptedJobs.ignoring : L.interruptedJobs.ignoreAll }}
      </button>
    </div>

    <div class="interrupted-list">
      <div v-for="job in system.interruptedJobs" :key="job.job_id" class="interrupted-item">
        <div class="item-info">
          <span class="item-kind">{{ kindLabel(job.kind) }}</span>
          <span class="item-id">{{ job.job_id.slice(0, 8) }}</span>
          <span v-if="job.progress" class="item-progress">{{ job.progress }}%</span>
          <span v-if="job.error" class="item-error">{{ job.error }}</span>
        </div>
        <div class="item-actions">
          <button class="btn btn-outline btn-xs" :disabled="acting" @click="handleRetrySingle(job.job_id)">
            {{ L.interruptedJobs.retry }}
          </button>
          <button class="btn btn-ghost btn-xs" :disabled="acting" @click="handleIgnoreSingle(job.job_id)">
            {{ L.interruptedJobs.ignore }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { labels as L } from '../../i18n/labels.js'
import { useSystemStore } from '../../stores/system.js'
import { useToastStore } from '../../stores/toast.js'

const system = useSystemStore()
const toast = useToastStore()
const acting = ref(null)

function kindLabel(kind) {
  return L.interruptedJobs.kindMap[kind] || L.interruptedJobs.kindMap.generic
}

async function handleRetryAll() {
  acting.value = 'retry'
  const data = await system.retryAllInterrupted()
  acting.value = null
  if (data && !data.error) {
    toast.show(L.interruptedJobs.retrySuccess.replace('{count}', data.retried || 0), 'success')
  }
}

async function handleIgnoreAll() {
  acting.value = 'ignore'
  const data = await system.ignoreAllInterrupted()
  acting.value = null
  if (data && !data.error) {
    toast.show(L.interruptedJobs.ignoreSuccess.replace('{count}', data.ignored || 0), 'info')
  }
}

async function handleRetrySingle(jobId) {
  acting.value = 'retry'
  const data = await system.retryAllInterrupted([jobId])
  acting.value = null
  if (data && !data.error) {
    toast.show(L.interruptedJobs.retrySuccess.replace('{count}', 1), 'success')
  }
}

async function handleIgnoreSingle(jobId) {
  acting.value = 'ignore'
  const data = await system.ignoreAllInterrupted([jobId])
  acting.value = null
  if (data && !data.error) {
    toast.show(L.interruptedJobs.ignoreSuccess.replace('{count}', 1), 'info')
  }
}
</script>

<style scoped>
.interrupted-panel {
  background: rgba(240, 173, 78, 0.08);
  border: 1px solid rgba(240, 173, 78, 0.25);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 16px;
}

.interrupted-header {
  margin-bottom: 12px;
}

.interrupted-title {
  font-size: 14px;
  font-weight: 600;
  display: block;
  margin-bottom: 4px;
}

.interrupted-desc {
  font-size: 12px;
  color: var(--muted);
}

.interrupted-actions-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.interrupted-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.interrupted-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.05));
  border-radius: 6px;
}

.item-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.item-kind {
  font-size: 12px;
  font-weight: 500;
  background: rgba(240, 173, 78, 0.15);
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

.item-id {
  font-size: 11px;
  font-family: monospace;
  color: var(--muted);
}

.item-progress {
  font-size: 11px;
  color: var(--muted);
}

.item-error {
  font-size: 11px;
  color: var(--danger, #ff3b30);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

/* ── Button styles (reuse project patterns) ── */
.btn { border: none; border-radius: 6px; cursor: pointer; font-size: 12px; transition: opacity 0.15s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 6px 14px; }
.btn-xs { padding: 4px 10px; font-size: 11px; }
.btn-primary { background: var(--accent, #007aff); color: #fff; }
.btn-outline { background: transparent; border: 1px solid var(--border, rgba(255,255,255,0.12)); color: var(--text); }
.btn-ghost { background: transparent; color: var(--muted); }
.btn-ghost:hover:not(:disabled) { color: var(--text); }
</style>
