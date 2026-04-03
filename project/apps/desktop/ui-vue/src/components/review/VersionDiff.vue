<script setup>
/**
 * VersionDiff.vue — R12: Visual diff between two versions.
 * Shows added (green), removed (red), modified (yellow) segments on timeline.
 */
import { computed } from 'vue'

const props = defineProps({
  diff: { type: Array, default: () => [] },       // DiffEntry[]
  summary: { type: String, default: '' },
  pxPerSec: { type: Number, default: 50 },
  edits: { type: Array, default: () => [] },       // current edit segments
})

const emit = defineEmits(['seek'])

const colorMap = {
  added: '#22c55e',
  removed: '#ef4444',
  modified: '#eab308',
}

const diffMarkers = computed(() =>
  props.diff.map(d => {
    const seg = d.segment || d.new_segment || d.old_segment || {}
    const startMs = seg.start_ms || 0
    const endMs = seg.end_ms || startMs + 2000
    return {
      ...d,
      left: (startMs / 1000) * props.pxPerSec,
      width: Math.max(4, ((endMs - startMs) / 1000) * props.pxPerSec),
      color: colorMap[d.action] || '#94a3b8',
    }
  })
)

function seekTo(marker) {
  const ms = marker.segment?.start_ms || marker.old_segment?.start_ms || 0
  emit('seek', ms)
}
</script>

<template>
  <div class="version-diff">
    <div v-if="summary" class="diff-summary">
      <span class="diff-label">变更摘要:</span>
      {{ summary }}
    </div>

    <div class="diff-track">
      <div
        v-for="(marker, i) in diffMarkers"
        :key="i"
        class="diff-marker"
        :style="{
          left: marker.left + 'px',
          width: marker.width + 'px',
          backgroundColor: marker.color,
        }"
        :title="`${marker.action} @ idx ${marker.idx}`"
        @click="seekTo(marker)"
      >
        <span class="diff-badge">{{ marker.action === 'added' ? '+' : marker.action === 'removed' ? '−' : '~' }}</span>
      </div>
    </div>

    <div class="diff-legend">
      <span class="legend-item"><span class="dot" style="background:#22c55e"></span>新增</span>
      <span class="legend-item"><span class="dot" style="background:#ef4444"></span>删除</span>
      <span class="legend-item"><span class="dot" style="background:#eab308"></span>修改</span>
    </div>
  </div>
</template>

<style scoped>
.version-diff { padding: 8px 0; }
.diff-summary {
  font-size: 12px; color: var(--text-muted, #94a3b8);
  margin-bottom: 6px;
}
.diff-label { font-weight: 600; }
.diff-track {
  position: relative; height: 24px;
  background: var(--bg-track, #1e293b); border-radius: 4px;
  overflow: hidden;
}
.diff-marker {
  position: absolute; top: 2px; height: 20px;
  border-radius: 3px; opacity: 0.7; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: opacity 0.15s;
}
.diff-marker:hover { opacity: 1; }
.diff-badge { font-size: 11px; font-weight: bold; color: #fff; }
.diff-legend {
  display: flex; gap: 12px; margin-top: 4px; font-size: 11px;
  color: var(--text-muted, #94a3b8);
}
.legend-item { display: flex; align-items: center; gap: 4px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
</style>
