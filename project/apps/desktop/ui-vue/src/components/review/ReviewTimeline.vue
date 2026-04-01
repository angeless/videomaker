<template>
  <div class="review-timeline" ref="timelineRef">
    <!-- Ruler (time ticks) -->
    <div class="rt-ruler" :style="rulerStyle">
      <div
        v-for="tick in ticks"
        :key="tick.ms"
        class="rt-tick"
        :class="{ 'rt-tick-major': tick.major }"
        :style="{ left: msToX(tick.ms) + 'px' }"
      >
        <span v-if="tick.major" class="rt-tick-label">{{ tick.label }}</span>
      </div>
    </div>

    <!-- Tracks container (scrolls horizontally with ruler) -->
    <div class="rt-tracks" :style="rulerStyle" @scroll="onScroll" ref="tracksRef">
      <!-- Playhead -->
      <div class="rt-playhead" :style="{ left: playheadX + 'px' }"></div>

      <!-- Loop region -->
      <div
        v-if="store.loopIn != null && store.loopOut != null"
        class="rt-loop-region"
        :style="loopRegionStyle"
      ></div>

      <!-- Named slots for sub-tracks -->
      <slot name="thumbnails"></slot>
      <slot name="waveform"></slot>
      <slot name="comments"></slot>
      <slot name="subtitles"></slot>
    </div>

    <!-- Zoom controls -->
    <div class="rt-zoom-bar">
      <button class="rt-zoom-btn" @click="zoomOut" title="缩小 (Ctrl+-)">−</button>
      <span class="rt-zoom-level">{{ Math.round(store.timelineScale * 100) }}%</span>
      <button class="rt-zoom-btn" @click="zoomIn" title="放大 (Ctrl+=)">+</button>
      <button class="rt-zoom-btn" @click="zoomFit" title="适配">Fit</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()
const timelineRef = ref(null)
const tracksRef = ref(null)

const emit = defineEmits(['seek'])

// ── Scale: pixels per second ──
const PX_PER_SEC_BASE = 80
const MIN_SCALE = 0.25
const MAX_SCALE = 8

const pxPerSec = computed(() => PX_PER_SEC_BASE * store.timelineScale)

const totalWidth = computed(() => {
  if (!store.durationMs) return 0
  return (store.durationMs / 1000) * pxPerSec.value
})

const rulerStyle = computed(() => ({
  width: totalWidth.value + 'px',
  minWidth: '100%',
}))

// ── Coordinate helpers ──
function msToX(ms) {
  return (ms / 1000) * pxPerSec.value
}

function xToMs(x) {
  return Math.round((x / pxPerSec.value) * 1000)
}

// ── Playhead ──
const playheadX = computed(() => msToX(store.currentTimeMs))

// ── Loop region ──
const loopRegionStyle = computed(() => {
  if (store.loopIn == null || store.loopOut == null) return {}
  return {
    left: msToX(store.loopIn) + 'px',
    width: msToX(store.loopOut - store.loopIn) + 'px',
  }
})

// ── Ruler ticks ──
const ticks = computed(() => {
  if (!store.durationMs) return []

  const result = []
  const durationS = store.durationMs / 1000

  // Adaptive tick interval based on zoom level
  let majorInterval // seconds
  if (pxPerSec.value >= 400) majorInterval = 1
  else if (pxPerSec.value >= 160) majorInterval = 5
  else if (pxPerSec.value >= 60) majorInterval = 10
  else if (pxPerSec.value >= 20) majorInterval = 30
  else majorInterval = 60

  const minorInterval = majorInterval / 5

  for (let s = 0; s <= durationS; s += minorInterval) {
    const ms = Math.round(s * 1000)
    const isMajor = Math.abs(s % majorInterval) < 0.001
    result.push({
      ms,
      major: isMajor,
      label: isMajor ? formatTime(s) : '',
    })
  }
  return result
})

function formatTime(totalS) {
  const m = Math.floor(totalS / 60)
  const s = Math.floor(totalS % 60)
  if (m === 0) return s + 's'
  return m + ':' + String(s).padStart(2, '0')
}

// ── Zoom ──
function zoomIn() {
  store.timelineScale = Math.min(MAX_SCALE, store.timelineScale * 1.5)
}

function zoomOut() {
  store.timelineScale = Math.max(MIN_SCALE, store.timelineScale / 1.5)
}

function zoomFit() {
  if (!store.durationMs || !timelineRef.value) return
  const containerWidth = timelineRef.value.clientWidth - 16 // padding
  const durationS = store.durationMs / 1000
  store.timelineScale = containerWidth / (durationS * PX_PER_SEC_BASE)
}

// ── Click to seek ──
function onScroll() {
  // Future: sync scroll position for virtual rendering
}

// ── Auto-scroll to follow playhead ──
watch(() => store.currentTimeMs, () => {
  if (!store.isPlaying || !timelineRef.value) return
  const container = timelineRef.value
  const headX = playheadX.value
  const scrollLeft = container.scrollLeft
  const viewWidth = container.clientWidth

  // Scroll when playhead exits the visible 60-90% zone
  if (headX > scrollLeft + viewWidth * 0.9) {
    container.scrollLeft = headX - viewWidth * 0.3
  } else if (headX < scrollLeft + viewWidth * 0.1) {
    container.scrollLeft = Math.max(0, headX - viewWidth * 0.3)
  }
})

// Expose for parent
defineExpose({ msToX, xToMs, pxPerSec, zoomIn, zoomOut, zoomFit })
</script>

<style scoped>
.review-timeline {
  position: relative;
  background: #111;
  border-top: 1px solid #333;
  overflow-x: auto;
  overflow-y: hidden;
  min-height: 120px;
  user-select: none;
}

/* Ruler */
.rt-ruler {
  position: relative;
  height: 24px;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
}

.rt-tick {
  position: absolute;
  top: 0;
  width: 1px;
  height: 6px;
  background: #555;
}

.rt-tick-major {
  height: 14px;
  background: #888;
}

.rt-tick-label {
  position: absolute;
  top: 14px;
  left: 2px;
  font-size: 0.6rem;
  color: #888;
  white-space: nowrap;
  font-family: 'SF Mono', 'Menlo', monospace;
}

/* Tracks */
.rt-tracks {
  position: relative;
  min-height: 96px;
}

/* Playhead */
.rt-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #ef4444;
  z-index: 10;
  pointer-events: none;
}

.rt-playhead::before {
  content: '';
  position: absolute;
  top: -2px;
  left: -4px;
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 6px solid #ef4444;
}

/* Loop region */
.rt-loop-region {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(234, 179, 8, 0.15);
  border-left: 1px solid #eab308;
  border-right: 1px solid #eab308;
  pointer-events: none;
  z-index: 5;
}

/* Zoom bar */
.rt-zoom-bar {
  position: absolute;
  bottom: 4px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(0, 0, 0, 0.7);
  padding: 2px 6px;
  border-radius: 4px;
  z-index: 20;
}

.rt-zoom-btn {
  background: none;
  border: none;
  color: #aaa;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 0.75rem;
  border-radius: 3px;
}

.rt-zoom-btn:hover {
  background: #333;
  color: #fff;
}

.rt-zoom-level {
  font-size: 0.65rem;
  color: #888;
  min-width: 32px;
  text-align: center;
  font-family: 'SF Mono', 'Menlo', monospace;
}
</style>
