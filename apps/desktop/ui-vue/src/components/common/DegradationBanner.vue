<template>
  <div v-if="items.length > 0" class="degradation-banner" :class="`severity-${maxSeverity}`">
    <div class="degradation-header" @click="expanded = !expanded">
      <span class="degradation-icon">⚠️</span>
      <span class="degradation-summary">
        {{ items.length }} 项功能降级
      </span>
      <button class="degradation-toggle">{{ expanded ? '收起' : '查看详情' }}</button>
    </div>
    <div v-if="expanded" class="degradation-list">
      <div v-for="(item, i) in items" :key="i" class="degradation-item">
        <span class="badge" :class="severityBadge(item.severity)">
          {{ severityLabel(item.severity) }}
        </span>
        <span class="degradation-feature">{{ item.feature }}</span>
        <span class="degradation-reason">{{ item.reason }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  // item: { feature: string, reason: string, severity: 'warning' | 'error' }
})

const expanded = ref(false)

const maxSeverity = computed(() => {
  if (props.items.some(i => i.severity === 'error')) return 'error'
  return 'warning'
})

function severityBadge(s) {
  return s === 'error' ? 'badge-danger' : 'badge-warn'
}

function severityLabel(s) {
  return s === 'error' ? '缺失' : '降级'
}
</script>

<style scoped>
.degradation-banner {
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}

.severity-warning {
  background: rgba(240, 173, 78, 0.1);
  border: 1px solid rgba(240, 173, 78, 0.3);
}

.severity-error {
  background: rgba(255, 59, 48, 0.08);
  border: 1px solid rgba(255, 59, 48, 0.3);
}

.degradation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
}

.degradation-icon {
  font-size: 14px;
}

.degradation-summary {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.degradation-toggle {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
}

.degradation-list {
  padding: 0 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.degradation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.degradation-feature {
  font-weight: 500;
  min-width: 80px;
}

.degradation-reason {
  color: var(--muted);
}
</style>
