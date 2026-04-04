<template>
  <div class="video-type-selector">
    <span class="vts-label">视频类型</span>
    <div class="vts-options">
      <button
        v-for="opt in options"
        :key="opt.value"
        class="vts-btn"
        :class="{ active: modelValue === opt.value }"
        @click="$emit('update:modelValue', opt.value)"
      >
        <span class="vts-icon">{{ opt.icon }}</span>
        <span class="vts-text">{{ opt.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: 'vlog' },
})

defineEmits(['update:modelValue'])

const options = [
  { value: 'vlog',      icon: '🎬', label: 'Vlog' },
  { value: 'tutorial',  icon: '📚', label: '教程' },
  { value: 'review',    icon: '🔍', label: '测评' },
  { value: 'interview', icon: '🎙️', label: '访谈' },
  { value: 'montage',   icon: '🎞️', label: '混剪' },
  { value: 'shorts',    icon: '📱', label: '短视频' },
]
</script>

<style scoped>
.video-type-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}
.vts-label {
  font-size: 12px;
  color: var(--text-muted, #9ca3af);
  white-space: nowrap;
}
.vts-options {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.vts-btn {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  background: transparent;
  color: #9ca3af;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}
.vts-btn:hover {
  border-color: rgba(59, 130, 246, 0.3);
  color: #d1d5db;
}
.vts-btn.active {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
}
.vts-icon { font-size: 13px; }
</style>
