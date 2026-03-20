<template>
  <div
    class="tl-playhead"
    :style="{ left: (labelOffset + timeToPx(store.playheadTime)) + 'px' }"
  >
    <div class="tl-playhead-handle" @mousedown.prevent="startDrag"></div>
    <div class="tl-playhead-line"></div>
  </div>
</template>

<script setup>
import { useTimelineStore } from '../../stores/timeline.js'
import { useTimeline } from '../../composables/useTimeline.js'

const props = defineProps({
  scrollContainer: { type: Object, default: null },
})

const store = useTimelineStore()
const { timeToPx, pxToTime } = useTimeline()

// Label spacer offset (48px for track labels)
const labelOffset = 48

function startDrag(e) {
  const onMove = (ev) => {
    const container = props.scrollContainer
    if (!container) return
    const rect = container.getBoundingClientRect()
    const scrollLeft = container.scrollLeft || 0
    const x = ev.clientX - rect.left - labelOffset + scrollLeft
    store.setPlayhead(pxToTime(Math.max(0, x)))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
</script>

<style scoped>
.tl-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  z-index: 5;
  pointer-events: none;
}

.tl-playhead-line {
  width: 1px;
  height: 100%;
  background: var(--danger, #f87171);
}

.tl-playhead-handle {
  width: 12px;
  height: 12px;
  background: var(--danger, #f87171);
  clip-path: polygon(50% 100%, 0% 0%, 100% 0%);
  position: absolute;
  top: 0;
  left: -6px;
  cursor: ew-resize;
  pointer-events: auto;
}
</style>
