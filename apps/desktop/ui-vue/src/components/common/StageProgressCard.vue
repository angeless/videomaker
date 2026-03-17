<template>
  <div class="stage-progress">
    <div v-for="(stage, i) in stages" :key="i" class="stage-item" :class="`stage-${stage.status}`">
      <div class="stage-header">
        <span class="stage-index">{{ i + 1 }}</span>
        <span class="stage-name">{{ stage.name }}</span>
        <span class="stage-status-text">{{ statusLabel(stage.status) }}</span>
      </div>

      <div v-if="stage.status === 'running' || stage.status === 'done'" class="stage-bar">
        <div class="stage-bar-fill" :style="{ width: (stage.progress || 0) + '%' }"></div>
      </div>

      <div v-if="stage.details" class="stage-details">
        <span v-if="stage.details.duration" class="stage-meta">{{ stage.details.duration }}</span>
        <span v-if="stage.details.size" class="stage-meta">{{ stage.details.size }}</span>
      </div>

      <!-- 内联降级警告 -->
      <div v-if="stage.degradations && stage.degradations.length > 0" class="stage-degradations">
        <span v-for="(d, j) in stage.degradations" :key="j" class="stage-degradation-tag">
          ⚠️ {{ d }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  stages: {
    type: Array,
    default: () => [],
    // stage: { name, status: 'pending'|'running'|'done'|'error', progress, details: { duration, size }, degradations: [] }
  },
})

function statusLabel(s) {
  const map = { pending: '等待中', running: '进行中', done: '完成', error: '失败', skipped: '跳过' }
  return map[s] || s
}
</script>

<style scoped>
.stage-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stage-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 14px;
  transition: border-color 0.2s;
}

.stage-item.stage-running {
  border-color: var(--accent);
  background: rgba(90, 141, 238, 0.03);
}

.stage-item.stage-done {
  border-color: #34c759;
}

.stage-item.stage-error {
  border-color: #ff3b30;
}

.stage-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stage-index {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--surface2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.stage-running .stage-index { background: var(--accent); color: #fff; }
.stage-done .stage-index { background: #34c759; color: #fff; }
.stage-error .stage-index { background: #ff3b30; color: #fff; }

.stage-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.stage-status-text {
  font-size: 11px;
  color: var(--muted);
}

.stage-bar {
  margin-top: 6px;
  height: 3px;
  background: var(--surface2);
  border-radius: 2px;
  overflow: hidden;
}

.stage-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.3s;
}

.stage-done .stage-bar-fill { background: #34c759; }

.stage-details {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}

.stage-meta {
  font-size: 11px;
  color: var(--muted);
}

.stage-degradations {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.stage-degradation-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(240, 173, 78, 0.15);
  color: #d4a020;
}
</style>
