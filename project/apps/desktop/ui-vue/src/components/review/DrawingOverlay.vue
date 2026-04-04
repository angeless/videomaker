<template>
  <div class="drawing-overlay" v-show="store.mode === 'drawing'" ref="containerRef">
    <canvas
      ref="canvasRef"
      :width="canvasSize.w"
      :height="canvasSize.h"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @mouseleave="onMouseUp"
    ></canvas>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const emit = defineEmits(['annotationComplete'])

const store = useReviewStore()
const containerRef = ref(null)
const canvasRef = ref(null)

const canvasSize = reactive({ w: 800, h: 450 })

// Drawing state
const tool = ref('pen')        // 'pen' | 'arrow' | 'rect' | 'circle' | 'text' | 'spotlight' | 'blur' | 'eraser'
const color = ref('#ef4444')
const lineWidth = ref(3)
const strokes = ref([])        // completed strokes
const currentStroke = ref(null) // in-progress stroke
const undoneStrokes = ref([])  // for redo
const isDrawing = ref(false)

// Resize canvas to match container
function updateCanvasSize() {
  if (!containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  canvasSize.w = Math.round(rect.width)
  canvasSize.h = Math.round(rect.height)
  nextTick(redraw)
}

// ── Mouse handlers ──
function onMouseDown(e) {
  isDrawing.value = true
  const pos = getPos(e)

  if (tool.value === 'text') {
    const text = prompt('输入标注文字:')
    if (text) {
      strokes.value.push({
        type: 'text',
        color: color.value,
        width: lineWidth.value,
        pos,
        text,
        fontSize: 16 + lineWidth.value * 4,
      })
      redraw()
      serializeToStore()
    }
    isDrawing.value = false
    return
  }

  if (tool.value === 'pen' || tool.value === 'eraser') {
    currentStroke.value = {
      type: tool.value,
      color: tool.value === 'eraser' ? 'eraser' : color.value,
      width: tool.value === 'eraser' ? lineWidth.value * 4 : lineWidth.value,
      points: [pos],
    }
  } else {
    currentStroke.value = {
      type: tool.value,
      color: color.value,
      width: lineWidth.value,
      start: pos,
      end: pos,
    }
  }
  undoneStrokes.value = []
}

function onMouseMove(e) {
  if (!isDrawing.value || !currentStroke.value) return
  const pos = getPos(e)

  if (currentStroke.value.type === 'pen' || currentStroke.value.type === 'eraser') {
    currentStroke.value.points.push(pos)
  } else {
    currentStroke.value.end = pos
  }
  redraw()
}

function onMouseUp() {
  if (!isDrawing.value || !currentStroke.value) return
  isDrawing.value = false
  strokes.value.push({ ...currentStroke.value })
  currentStroke.value = null
  redraw()
  serializeToStore()
  emitAnnotationComplete()
}

function getPos(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) / rect.width,
    y: (e.clientY - rect.top) / rect.height,
  }
}

// ── Render ──
function redraw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  for (const s of strokes.value) {
    drawStroke(ctx, s)
  }
  if (currentStroke.value) {
    drawStroke(ctx, currentStroke.value)
  }
}

function drawStroke(ctx, s) {
  const w = canvasSize.w
  const h = canvasSize.h
  ctx.strokeStyle = s.color
  ctx.fillStyle = s.color
  ctx.lineWidth = s.width
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  if (s.type === 'eraser' && s.points?.length > 1) {
    ctx.save()
    ctx.globalCompositeOperation = 'destination-out'
    ctx.lineWidth = s.width
    ctx.beginPath()
    ctx.moveTo(s.points[0].x * w, s.points[0].y * h)
    for (let i = 1; i < s.points.length; i++) {
      ctx.lineTo(s.points[i].x * w, s.points[i].y * h)
    }
    ctx.stroke()
    ctx.restore()
    return
  }

  if (s.type === 'text' && s.pos) {
    ctx.save()
    ctx.font = `${s.fontSize || 20}px "PingFang SC", sans-serif`
    ctx.fillStyle = s.color
    ctx.fillText(s.text || '', s.pos.x * w, s.pos.y * h)
    ctx.restore()
    return
  }

  if (s.type === 'spotlight' && s.start && s.end) {
    // Dim entire canvas, then clear the spotlight region
    ctx.save()
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
    ctx.fillRect(0, 0, w, h)
    ctx.globalCompositeOperation = 'destination-out'
    const sx = Math.min(s.start.x, s.end.x) * w
    const sy = Math.min(s.start.y, s.end.y) * h
    const sw = Math.abs(s.end.x - s.start.x) * w
    const sh = Math.abs(s.end.y - s.start.y) * h
    ctx.fillStyle = 'white'
    ctx.beginPath()
    ctx.ellipse(sx + sw / 2, sy + sh / 2, sw / 2, sh / 2, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
    // Draw border around spotlight
    ctx.strokeStyle = s.color
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.ellipse(
      (Math.min(s.start.x, s.end.x) + Math.abs(s.end.x - s.start.x) / 2) * w,
      (Math.min(s.start.y, s.end.y) + Math.abs(s.end.y - s.start.y) / 2) * h,
      Math.abs(s.end.x - s.start.x) * w / 2,
      Math.abs(s.end.y - s.start.y) * h / 2,
      0, 0, Math.PI * 2,
    )
    ctx.stroke()
    return
  }

  if (s.type === 'blur' && s.start && s.end) {
    // Simulate blur with semi-transparent overlay + hatching pattern
    const bx = Math.min(s.start.x, s.end.x) * w
    const by = Math.min(s.start.y, s.end.y) * h
    const bw = Math.abs(s.end.x - s.start.x) * w
    const bh = Math.abs(s.end.y - s.start.y) * h
    ctx.save()
    ctx.fillStyle = 'rgba(128, 128, 128, 0.4)'
    ctx.fillRect(bx, by, bw, bh)
    // Hatching lines to visually indicate blur
    ctx.strokeStyle = 'rgba(128, 128, 128, 0.3)'
    ctx.lineWidth = 1
    for (let i = 0; i < bw + bh; i += 6) {
      ctx.beginPath()
      ctx.moveTo(bx + Math.min(i, bw), by + Math.max(0, i - bw))
      ctx.lineTo(bx + Math.max(0, i - bh), by + Math.min(i, bh))
      ctx.stroke()
    }
    ctx.strokeStyle = s.color
    ctx.lineWidth = 2
    ctx.setLineDash([4, 4])
    ctx.strokeRect(bx, by, bw, bh)
    ctx.setLineDash([])
    ctx.restore()
    return
  }

  if (s.type === 'pen' && s.points?.length > 1) {
    ctx.beginPath()
    ctx.moveTo(s.points[0].x * w, s.points[0].y * h)
    for (let i = 1; i < s.points.length; i++) {
      ctx.lineTo(s.points[i].x * w, s.points[i].y * h)
    }
    ctx.stroke()
  } else if (s.type === 'arrow' && s.start && s.end) {
    const sx = s.start.x * w, sy = s.start.y * h
    const ex = s.end.x * w, ey = s.end.y * h
    ctx.beginPath()
    ctx.moveTo(sx, sy)
    ctx.lineTo(ex, ey)
    ctx.stroke()
    // Arrowhead
    const angle = Math.atan2(ey - sy, ex - sx)
    const headLen = 12
    ctx.beginPath()
    ctx.moveTo(ex, ey)
    ctx.lineTo(ex - headLen * Math.cos(angle - 0.4), ey - headLen * Math.sin(angle - 0.4))
    ctx.lineTo(ex - headLen * Math.cos(angle + 0.4), ey - headLen * Math.sin(angle + 0.4))
    ctx.closePath()
    ctx.fill()
  } else if (s.type === 'rect' && s.start && s.end) {
    const x = Math.min(s.start.x, s.end.x) * w
    const y = Math.min(s.start.y, s.end.y) * h
    const rw = Math.abs(s.end.x - s.start.x) * w
    const rh = Math.abs(s.end.y - s.start.y) * h
    ctx.strokeRect(x, y, rw, rh)
  } else if (s.type === 'circle' && s.start && s.end) {
    const cx = ((s.start.x + s.end.x) / 2) * w
    const cy = ((s.start.y + s.end.y) / 2) * h
    const rx = Math.abs(s.end.x - s.start.x) * w / 2
    const ry = Math.abs(s.end.y - s.start.y) * h / 2
    ctx.beginPath()
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
    ctx.stroke()
  }
}

// ── Undo / Redo ──
function undo() {
  if (strokes.value.length === 0) return
  undoneStrokes.value.push(strokes.value.pop())
  redraw()
  serializeToStore()
}

function redo() {
  if (undoneStrokes.value.length === 0) return
  strokes.value.push(undoneStrokes.value.pop())
  redraw()
  serializeToStore()
}

function clear() {
  strokes.value = []
  undoneStrokes.value = []
  redraw()
  serializeToStore()
}

// ── Serialize drawing data to store ──
function serializeToStore() {
  if (strokes.value.length === 0) {
    store.drawingData = null
    return
  }
  store.drawingData = JSON.stringify(strokes.value)
}

// ── R8 (v0.17.0): Debounced annotation complete event ──
let _annotationTimer = null

function emitAnnotationComplete() {
  if (_annotationTimer) clearTimeout(_annotationTimer)
  _annotationTimer = setTimeout(() => {
    if (strokes.value.length === 0) return
    // Capture current video frame as data URL
    let frameDataUrl = null
    try {
      const video = document.querySelector('.review-player video')
      if (video) {
        const c = document.createElement('canvas')
        c.width = video.videoWidth || video.clientWidth
        c.height = video.videoHeight || video.clientHeight
        c.getContext('2d').drawImage(video, 0, 0, c.width, c.height)
        frameDataUrl = c.toDataURL('image/jpeg', 0.85)
      }
    } catch (e) {
      // tainted canvas or no video — proceed without frame
    }
    emit('annotationComplete', {
      strokes: JSON.parse(JSON.stringify(strokes.value)),
      frameDataUrl,
      timestamp_ms: store.currentTimeMs || 0,
    })
  }, 500) // 500ms debounce
}

// ── Load from store (for editing existing drawing) ──
function loadFromStore() {
  if (!store.drawingData) {
    strokes.value = []
    return
  }
  try {
    strokes.value = JSON.parse(store.drawingData)
  } catch {
    strokes.value = []
  }
  redraw()
}

// Watch for entering drawing mode
watch(() => store.mode, (mode) => {
  if (mode === 'drawing') {
    nextTick(() => {
      updateCanvasSize()
      loadFromStore()
    })
  }
})

// Expose for parent and keyboard handler
defineExpose({ tool, color, lineWidth, undo, redo, clear, updateCanvasSize })
</script>

<style scoped>
.drawing-overlay {
  position: absolute;
  inset: 0;
  z-index: 15;
  cursor: crosshair;
}

.drawing-overlay canvas {
  width: 100%;
  height: 100%;
}
</style>
