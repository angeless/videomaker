<template>
  <div
    class="scene-card"
    :class="{ selected: scene.selected }"
    @click="$emit('toggle', scene.scene_idx)"
  >
    <!-- Thumbnail -->
    <div class="sc-thumb">
      <img v-if="scene.thumbnail_path" :src="scene.thumbnail_path" alt="" />
      <div v-else class="sc-thumb-placeholder">{{ scene.scene_idx + 1 }}</div>
      <span v-if="scene.scene_type" class="sc-type-badge">{{ scene.scene_type }}</span>
      <span class="sc-duration-badge">{{ durationLabel }}</span>
    </div>

    <!-- Info row -->
    <div class="sc-info">
      <span class="sc-time">{{ formatTime(scene.start_ms) }}</span>
      <span v-if="scene.quality_score" class="sc-quality" :style="qualityColor">
        {{ scene.quality_score.toFixed(1) }}
      </span>
    </div>

    <!-- Selection check -->
    <div class="sc-check">
      <span v-if="scene.selected" class="sc-check-icon">✓</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  scene: { type: Object, required: true },
})

defineEmits(['toggle'])

const durationLabel = computed(() => {
  const s = (props.scene.duration_ms || 0) / 1000
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m${Math.round(s % 60)}s`
})

const qualityColor = computed(() => {
  const q = props.scene.quality_score || 0
  if (q >= 0.8) return { color: '#22c55e' }
  if (q >= 0.5) return { color: '#f59e0b' }
  return { color: '#ef4444' }
})

function formatTime(ms) {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.scene-card {
  border: 2px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.1s;
  overflow: hidden;
  background: var(--bg-card, rgba(255, 255, 255, 0.04));
}
.scene-card:hover {
  border-color: rgba(59, 130, 246, 0.3);
  transform: scale(1.02);
}
.scene-card.selected {
  border-color: #3b82f6;
}

.sc-thumb {
  position: relative;
  aspect-ratio: 16/9;
  background: #0f0f1a;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sc-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.sc-thumb-placeholder {
  font-size: 20px;
  font-weight: 700;
  color: #4b5563;
}

.sc-type-badge,
.sc-duration-badge {
  position: absolute;
  background: rgba(0, 0, 0, 0.7);
  color: #aaa;
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
}
.sc-type-badge { top: 4px; right: 4px; }
.sc-duration-badge { bottom: 4px; right: 4px; color: #ddd; }

.sc-info {
  padding: 4px 8px;
  font-size: 11px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sc-time { color: var(--text-muted, #9ca3af); }
.sc-quality { font-weight: 600; font-variant-numeric: tabular-nums; }

.sc-check {
  text-align: center;
  min-height: 20px;
  padding-bottom: 4px;
}
.sc-check-icon {
  color: #3b82f6;
  font-size: 14px;
  font-weight: 700;
}
</style>
