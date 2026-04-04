<template>
  <div class="track-comments">
    <div
      v-for="comment in store.filteredComments"
      :key="comment.id"
      class="tc-marker"
      :class="{
        resolved: comment.status === 'resolved',
        active: activeId === comment.id,
      }"
      :style="markerStyle(comment)"
      :title="comment.text"
      @click.stop="onClickMarker(comment)"
      @mouseenter="activeId = comment.id"
      @mouseleave="activeId = null"
    >
      <span class="tc-marker-icon">{{ typeIcon(comment.comment_type) }}</span>
      <!-- Range bar for comments with time_end_ms -->
      <div
        v-if="comment.time_end_ms"
        class="tc-range-bar"
        :style="rangeBarStyle(comment)"
      ></div>
    </div>

    <!-- Tooltip -->
    <div v-if="activeComment" class="tc-tooltip" :style="tooltipStyle">
      <span class="tc-tooltip-type" :style="{ color: typeColor(activeComment.comment_type) }">
        {{ typeLabel(activeComment.comment_type) }}
      </span>
      <span class="tc-tooltip-text">{{ activeComment.text }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useReviewStore } from '../../stores/review.js'
import { COMMENT_TYPES } from '../../config/shortcuts.js'

const store = useReviewStore()

const props = defineProps({
  pxPerSec: { type: Number, required: true },
})

const emit = defineEmits(['seek'])

const activeId = ref(null)

const activeComment = computed(() => {
  if (!activeId.value) return null
  return store.filteredComments.find(c => c.id === activeId.value)
})

function msToX(ms) {
  return (ms / 1000) * props.pxPerSec
}

function markerStyle(comment) {
  const ct = COMMENT_TYPES.find(c => c.type === comment.comment_type)
  return {
    left: msToX(comment.time_start_ms) + 'px',
    '--marker-color': ct?.color || '#9ca3af',
  }
}

function rangeBarStyle(comment) {
  const width = msToX(comment.time_end_ms - comment.time_start_ms)
  return { width: Math.max(4, width) + 'px' }
}

const tooltipStyle = computed(() => {
  if (!activeComment.value) return { display: 'none' }
  return { left: msToX(activeComment.value.time_start_ms) + 'px' }
})

function typeIcon(type) {
  return COMMENT_TYPES.find(c => c.type === type)?.icon || '⚪'
}

function typeColor(type) {
  return COMMENT_TYPES.find(c => c.type === type)?.color || '#9ca3af'
}

function typeLabel(type) {
  return COMMENT_TYPES.find(c => c.type === type)?.label || '通用'
}

function onClickMarker(comment) {
  emit('seek', comment.time_start_ms)
}
</script>

<style scoped>
.track-comments {
  position: relative;
  height: 24px;
  width: 100%;
}

.tc-marker {
  position: absolute;
  top: 2px;
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transform: translateX(-7px);
  z-index: 5;
  transition: transform 0.1s;
}

.tc-marker:hover,
.tc-marker.active {
  transform: translateX(-7px) scale(1.3);
  z-index: 10;
}

.tc-marker.resolved {
  opacity: 0.4;
}

.tc-marker-icon {
  font-size: 0.65rem;
  line-height: 1;
  filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.5));
}

.tc-range-bar {
  position: absolute;
  top: 12px;
  left: 7px;
  height: 3px;
  background: var(--marker-color);
  opacity: 0.5;
  border-radius: 1px;
  pointer-events: none;
}

/* Tooltip */
.tc-tooltip {
  position: absolute;
  bottom: 100%;
  margin-bottom: 4px;
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 4px 8px;
  max-width: 200px;
  z-index: 20;
  pointer-events: none;
  transform: translateX(-50%);
}

.tc-tooltip-type {
  font-size: 0.6rem;
  font-weight: 600;
  display: block;
}

.tc-tooltip-text {
  font-size: 0.65rem;
  color: #ccc;
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
