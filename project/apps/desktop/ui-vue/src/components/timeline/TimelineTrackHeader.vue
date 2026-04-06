<template>
  <div class="track-header" :class="'th-' + track.track_type">
    <span class="th-icon">{{ typeIcon }}</span>
    <span class="th-label">{{ track.label || track.track_type }}</span>
    <div class="th-controls">
      <button
        v-if="track.track_type !== 'subtitle'"
        class="th-btn"
        :class="{ active: track.locked }"
        @click="$emit('toggle-lock', track.track_id)"
        title="锁定"
      >🔒</button>
      <button
        v-if="track.track_type === 'audio'"
        class="th-btn"
        :class="{ active: track.muted }"
        @click="$emit('toggle-mute', track.track_id)"
        title="静音"
      >🔇</button>
      <input
        v-if="track.track_type === 'audio'"
        type="range"
        min="0" max="2" step="0.1"
        :value="track.volume"
        @input="$emit('set-volume', track.track_id, Number($event.target.value))"
        class="th-volume"
        title="音量"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  track: { type: Object, required: true },
})

defineEmits(['toggle-lock', 'toggle-mute', 'set-volume'])

const typeIcon = computed(() => {
  const icons = { video: '🎬', audio: '🔊', subtitle: '🅃', effect: '✨' }
  return icons[props.track.track_type] || '📦'
})
</script>

<style scoped>
.track-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  min-width: 120px;
  background: #1a1a2e;
  border-right: 1px solid #333;
  font-size: 0.75rem;
  color: #ccc;
}

.th-icon { font-size: 0.85rem; }
.th-label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.th-controls { display: flex; align-items: center; gap: 4px; }

.th-btn {
  background: none;
  border: 1px solid transparent;
  font-size: 0.7rem;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  opacity: 0.5;
}
.th-btn.active { opacity: 1; border-color: #555; }
.th-btn:hover { opacity: 0.8; }

.th-volume { width: 50px; height: 12px; }
</style>
