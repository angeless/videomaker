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

const store = useReviewStore()
const containerRef = ref(null)
const canvasRef = ref(null)

const canvasSize = reactive({ w: 800, h: 450 })

// Drawing state
const tool = ref('pen')        // 'pen' | 'arrow' | 'rect' | 'circle' | 'text'
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

  if (tool.value === 'pen') {
    currentStroke.value = {
      type: 'pen',
      color: color.value,
      width: lineWidth.value,
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

  if (currentStroke.value.type === 'pen') {
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
