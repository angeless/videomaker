<template>
  <div class="roughcut-stats">
    <div class="rs-item">
      <span class="rs-label">原始</span>
      <span class="rs-value">{{ formatDuration(totalDurationMs) }}</span>
    </div>
    <div class="rs-item rs-deleted">
      <span class="rs-label">已删</span>
      <span class="rs-value">{{ formatDuration(deletedDurationMs) }}</span>
    </div>
    <div class="rs-item rs-estimate">
      <span class="rs-label">预计</span>
      <span class="rs-value">{{ formatDuration(estimatedDurationMs) }}</span>
    </div>
    <div class="rs-sep"></div>
    <div class="rs-item">
      <span class="rs-label">语气词</span>
      <span class="rs-value">{{ fillerCount }}</span>
    </div>
    <div class="rs-item">
      <span class="rs-label">重复</span>
      <span class="rs-value">{{ retakeCount }}</span>
    </div>
    <div class="rs-item">
      <span class="rs-label">静音</span>
      <span class="rs-value">{{ silenceCount }}</span>
    </div>
    <div v-if="hookIdx !== null" class="rs-item rs-hook">
      <span class="rs-label">Hook</span>
      <span class="rs-value">¶{{ hookIdx }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  totalDurationMs: { type: Number, default: 0 },
  deletedDurationMs: { type: Number, default: 0 },
  estimatedDurationMs: { type: Number, default: 0 },
  fillerCount: { type: Number, default: 0 },
  retakeCount: { type: Number, default: 0 },
  silenceCount: { type: Number, default: 0 },
  hookIdx: { type: Number, default: null },
})

function formatDuration(ms) {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.roughcut-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted, #9ca3af);
}

.rs-item {
  display: flex;
  gap: 4px;
  white-space: nowrap;
}

.rs-label { color: #6b7280; }
.rs-value { font-variant-numeric: tabular-nums; }
.rs-deleted .rs-value { color: #ef4444; }
.rs-estimate .rs-value { color: #22c55e; font-weight: 600; }
.rs-hook .rs-value { color: #f59e0b; font-weight: 600; }

.rs-sep {
  width: 1px;
  height: 14px;
  background: rgba(255, 255, 255, 0.1);
}
</style>
