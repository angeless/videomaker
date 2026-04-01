<template>
  <div class="subtitle-editor" v-if="subtitles.length">
    <div
      v-for="sub in subtitles"
      :key="sub.id || sub.index"
      class="se-block"
      :class="{ active: isActive(sub) }"
      :style="blockStyle(sub)"
      @click="$emit('seek', sub.start_ms)"
    >
      <span class="se-text">{{ sub.text }}</span>
    </div>
  </div>
  <div class="subtitle-editor se-empty" v-else>
    <span class="se-placeholder">无字幕数据</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()

const props = defineProps({
  pxPerSec: { type: Number, required: true },
  subtitles: { type: Array, default: () => [] },
})

const emit = defineEmits(['seek'])

function blockStyle(sub) {
  const x = (sub.start_ms / 1000) * props.pxPerSec
  const w = ((sub.end_ms - sub.start_ms) / 1000) * props.pxPerSec
  return {
    left: x + 'px',
    width: Math.max(4, w) + 'px',
  }
}

function isActive(sub) {
  const t = store.currentTimeMs
  return t >= sub.start_ms && t <= sub.end_ms
}
</script>

<style scoped>
.subtitle-editor {
  position: relative;
  height: 24px;
  width: 100%;
}

.se-block {
  position: absolute;
  top: 2px;
  height: 20px;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 3px;
  display: flex;
  align-items: center;
  padding: 0 4px;
  cursor: pointer;
  overflow: hidden;
  transition: background 0.15s;
}

.se-block:hover {
  background: #333;
}

.se-block.active {
  background: #1e3a5f;
  border-color: #3b82f6;
}

.se-text {
  font-size: 0.55rem;
  color: #ccc;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.se-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  background: #111;
}

.se-placeholder {
  font-size: 0.6rem;
  color: #444;
}
</style>
