<template>
  <div class="tl-ruler" :style="{ width: totalWidth + 'px' }">
    <div class="tl-ruler-label-spacer"></div>
    <canvas ref="canvasRef" class="tl-ruler-canvas" :width="totalWidth" :height="28"></canvas>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import { useTimelineStore } from '../../stores/timeline.js'
import { useTimeline } from '../../composables/useTimeline.js'
import { useFormatters } from '../../composables/useFormatters.js'

const store = useTimelineStore()
const { pxPerSecond, totalWidth } = useTimeline()
const { formatDuration } = useFormatters()

const canvasRef = ref(null)

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const w = canvas.width
  const h = canvas.height
  if (!w || !h) return

  ctx.clearRect(0, 0, w, h)

  const pps = pxPerSecond.value
  const dur = store.totalDuration

  // Determine tick interval based on zoom
  let majorInterval, minorInterval
  if (pps < 30) {
    majorInterval = 30; minorInterval = 10
  } else if (pps < 90) {
    majorInterval = 10; minorInterval = 5
  } else if (pps < 200) {
    majorInterval = 5; minorInterval = 1
  } else {
    majorInterval = 2; minorInterval = 0.5
  }

  // Draw ticks
  ctx.strokeStyle = '#3a3a3a'
  ctx.fillStyle = '#6b7280'
  ctx.font = '10px -apple-system, BlinkMacSystemFont, sans-serif'
  ctx.textAlign = 'center'

  for (let t = 0; t <= dur + 0.01; t += minorInterval) {
    const x = Math.round(t * pps)
    if (x > w) break

    const isMajor = Math.abs(t % majorInterval) < 0.01 || Math.abs(t % majorInterval - majorInterval) < 0.01

    ctx.beginPath()
    ctx.moveTo(x + 0.5, h)
    ctx.lineTo(x + 0.5, isMajor ? h - 14 : h - 8)
    ctx.stroke()

    if (isMajor) {
      ctx.fillText(formatDuration(t), x, 12)
    }
  }
}

onMounted(() => nextTick(draw))
watch([() => store.zoom, () => store.totalDuration, totalWidth], () => nextTick(draw))
</script>

<style scoped>
.tl-ruler {
  display: flex;
  align-items: stretch;
  height: 28px;
  border-bottom: 1px solid var(--border);
}

.tl-ruler-label-spacer {
  width: 48px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  position: sticky;
  left: 0;
  background: var(--surface);
  z-index: 3;
}

.tl-ruler-canvas {
  display: block;
}
</style>
