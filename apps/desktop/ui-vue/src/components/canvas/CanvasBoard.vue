<template>
  <div
    ref="boardRef"
    class="canvas-board"
    @wheel.prevent="onWheel"
    @mousedown="onBoardMouseDown"
    @dragover.prevent="onDragOver"
    @drop.prevent="onDrop"
    @click="onBoardClick"
  >
    <div class="canvas-transform" :style="transformStyle">
      <!-- SVG layer for edges -->
      <svg class="edges-svg" :style="svgStyle">
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="var(--accent, #5a8dee)" opacity="0.6" />
          </marker>
        </defs>
        <CanvasEdge v-for="edge in canvas.edges" :key="edge.id" :edge="edge" />
        <!-- Temporary edge while dragging -->
        <path v-if="draggingFrom" :d="tempEdgePath" class="temp-edge" />
      </svg>

      <!-- Nodes layer -->
      <CanvasNode
        v-for="node in canvas.nodes"
        :key="node.id"
        :node="node"
        @port-drag-start="onPortDragStart"
        @port-drop="onPortDrop"
      />
    </div>

    <!-- Empty state -->
    <div v-if="canvas.nodeCount === 0" class="board-empty">
      <div class="board-empty-icon">🧩</div>
      <div class="board-empty-text">从左侧拖拽能力节点到此处</div>
    </div>

    <!-- Minimap -->
    <CanvasMinimap :board-width="boardWidth" :board-height="boardHeight" />

    <!-- Zoom indicator -->
    <div class="zoom-badge">{{ Math.round(canvas.viewport.zoom * 100) }}%</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'
import CanvasNode from './CanvasNode.vue'
import CanvasEdge from './CanvasEdge.vue'
import CanvasMinimap from './CanvasMinimap.vue'

const canvas = useCanvasStore()
const boardRef = ref(null)
const boardWidth = ref(1000)
const boardHeight = ref(700)

// ── Pan/Zoom ──
const transformStyle = computed(() => {
  const v = canvas.viewport
  return { transform: `translate(${v.panX}px, ${v.panY}px) scale(${v.zoom})` }
})

const svgStyle = computed(() => ({
  width: '10000px',
  height: '10000px',
  position: 'absolute',
  top: '0',
  left: '0',
  pointerEvents: 'none',
}))

function onWheel(e) {
  if (e.ctrlKey || e.metaKey) {
    // Zoom
    const delta = e.deltaY > 0 ? -0.08 : 0.08
    const rect = boardRef.value.getBoundingClientRect()
    canvas.zoomAt(delta, e.clientX - rect.left, e.clientY - rect.top)
  } else {
    // Pan
    canvas.pan(-e.deltaX, -e.deltaY)
  }
}

let isPanning = false
let panStartX = 0
let panStartY = 0

function onBoardMouseDown(e) {
  // Only pan on empty area (not on nodes)
  if (e.target !== boardRef.value && !e.target.classList.contains('canvas-transform') &&
      !e.target.classList.contains('edges-svg') && !e.target.classList.contains('board-empty') &&
      !e.target.classList.contains('board-empty-icon') && !e.target.classList.contains('board-empty-text')) return
  isPanning = true
  panStartX = e.clientX
  panStartY = e.clientY
  document.addEventListener('mousemove', onPanMove)
  document.addEventListener('mouseup', onPanEnd)
}

function onPanMove(e) {
  if (!isPanning) return
  canvas.pan(e.clientX - panStartX, e.clientY - panStartY)
  panStartX = e.clientX
  panStartY = e.clientY
}

function onPanEnd() {
  isPanning = false
  document.removeEventListener('mousemove', onPanMove)
  document.removeEventListener('mouseup', onPanEnd)
}

function onBoardClick() {
  canvas.clearSelection()
}

// ── Drop from palette ──
function onDragOver(e) {
  e.dataTransfer.dropEffect = 'copy'
}

function onDrop(e) {
  const raw = e.dataTransfer.getData('application/canvas-node')
  if (!raw) return
  try {
    const data = JSON.parse(raw)
    const rect = boardRef.value.getBoundingClientRect()
    const v = canvas.viewport
    const x = (e.clientX - rect.left - v.panX) / v.zoom - 90
    const y = (e.clientY - rect.top - v.panY) / v.zoom - 36
    canvas.addNode(data.capability_id, data.label, Math.round(x), Math.round(y))
  } catch { /* ignore bad data */ }
}

// ── Edge drawing ──
const draggingFrom = ref('')
const tempEdgeEnd = ref({ x: 0, y: 0 })

const tempEdgePath = computed(() => {
  if (!draggingFrom.value) return ''
  const fromNode = canvas.nodes.find(n => n.id === draggingFrom.value)
  if (!fromNode) return ''
  const sx = fromNode.x + fromNode.width / 2
  const sy = fromNode.y + (fromNode.height || 72) + 6
  const tx = tempEdgeEnd.value.x
  const ty = tempEdgeEnd.value.y
  const cp = Math.max(40, Math.abs(ty - sy) * 0.4)
  return `M ${sx},${sy} C ${sx},${sy + cp} ${tx},${ty - cp} ${tx},${ty}`
})

function onPortDragStart(nodeId) {
  draggingFrom.value = nodeId
  document.addEventListener('mousemove', onEdgeDragMove)
  document.addEventListener('mouseup', onEdgeDragEnd)
}

function onEdgeDragMove(e) {
  const rect = boardRef.value.getBoundingClientRect()
  const v = canvas.viewport
  tempEdgeEnd.value = {
    x: (e.clientX - rect.left - v.panX) / v.zoom,
    y: (e.clientY - rect.top - v.panY) / v.zoom,
  }
}

function onEdgeDragEnd() {
  draggingFrom.value = ''
  document.removeEventListener('mousemove', onEdgeDragMove)
  document.removeEventListener('mouseup', onEdgeDragEnd)
}

function onPortDrop(toNodeId) {
  if (draggingFrom.value && draggingFrom.value !== toNodeId) {
    canvas.addEdge(draggingFrom.value, toNodeId)
  }
  draggingFrom.value = ''
}

// ── Keyboard ──
function onKeyDown(e) {
  if (e.key === 'Delete' || e.key === 'Backspace') {
    // Don't delete if user is typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
    canvas.deleteSelected()
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown)
  // Track board dimensions for minimap
  if (boardRef.value) {
    boardWidth.value = boardRef.value.clientWidth
    boardHeight.value = boardRef.value.clientHeight
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
})
</script>

<style scoped>
.canvas-board {
  flex: 1;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle, var(--border, #333) 1px, transparent 1px);
  background-size: 24px 24px;
  cursor: grab;
}

.canvas-board:active {
  cursor: grabbing;
}

.canvas-transform {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  will-change: transform;
}

.edges-svg {
  overflow: visible;
}

.edges-svg :deep(.edge-path),
.edges-svg :deep(.edge-hit-area) {
  pointer-events: auto;
}

.temp-edge {
  fill: none;
  stroke: var(--accent, #5a8dee);
  stroke-width: 2;
  stroke-dasharray: 6 4;
  opacity: 0.5;
  pointer-events: none;
}

.board-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
  opacity: 0.4;
}

.board-empty-icon {
  font-size: 56px;
  margin-bottom: 8px;
}

.board-empty-text {
  font-size: 14px;
  color: var(--muted, #888);
}

.zoom-badge {
  position: absolute;
  bottom: 12px;
  right: 12px;
  background: var(--surface, #1a1a2e);
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--muted, #888);
  pointer-events: none;
}
</style>
