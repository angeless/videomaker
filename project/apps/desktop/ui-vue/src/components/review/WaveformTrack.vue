<template>
  <canvas
    ref="canvasRef"
    class="waveform-track"
    :width="canvasWidth"
    :height="40"
  ></canvas>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()
const canvasRef = ref(null)

const props = defineProps({
  pxPerSec: { type: Number, required: true },
})

const canvasWidth = computed(() => {
  if (!store.durationMs) return 300
  return Math.ceil((store.durationMs / 1000) * props.pxPerSec)
})

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const w = canvas.width
  const h = canvas.height

  ctx.clearRect(0, 0, w, h)

  const wd = store.waveformData
  if (!wd || !wd.peaks || wd.peaks.length === 0) {
    // Draw empty placeholder
    ctx.fillStyle = '#333'
    ctx.fillRect(0, h / 2 - 0.5, w, 1)
    return
  }

  const peaks = wd.peaks
  const barWidth = w / peaks.length
  const mid = h / 2

  ctx.fillStyle = '#3b82f6'

  for (let i = 0; i < peaks.length; i++) {
    const amp = peaks[i] * mid
    const x = i * barWidth
    ctx.fillRect(x, mid - amp, Math.max(1, barWidth - 0.5), amp * 2)
  }

  // Playhead position overlay
  if (store.durationMs > 0) {
    const playX = (store.currentTimeMs / store.durationMs) * w
    ctx.fillStyle = 'rgba(239, 68, 68, 0.6)'
    ctx.fillRect(playX, 0, 1, h)
  }
}

watch([() => store.waveformData, () => props.pxPerSec, canvasWidth], draw)
watch(() => store.currentTimeMs, draw)

onMounted(draw)
</script>

<style scoped>
.waveform-track {
  display: block;
  height: 40px;
  background: #111;
}
</style>
