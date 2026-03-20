<template>
  <div
    class="workflow-canvas"
    ref="canvasRef"
    @mousedown="onCanvasMouseDown"
    @wheel.prevent="onWheel"
    @mouseup="onCanvasMouseUp"
    @mousemove="onCanvasMouseMove"
  >
    <div
      class="canvas-transform"
      :style="transformStyle"
    >
      <!-- SVG 层：连线 -->
      <svg class="canvas-svg" xmlns="http://www.w3.org/2000/svg">
        <CanvasEdge
          v-for="edge in canvasStore.edges"
          :key="edge.id"
          :edge="edge"
          :from-node="nodeMap[edge.from]"
          :to-node="nodeMap[edge.to]"
          @remove="canvasStore.removeEdge"
        />
        <!-- 正在拖拽的临时连线 -->
        <path v-if="draggingEdge" :d="draggingEdgePath" class="dragging-edge" />
      </svg>

      <!-- 节点层 -->
      <CanvasNode
        v-for="node in canvasStore.nodes"
        :key="node.id"
        :node="node"
        :is-selected="canvasStore.selectedNodeId === node.id"
        :status="canvasStore.nodeStatuses[node.id] || 'idle'"
        @select="canvasStore.selectNode"
        @remove="canvasStore.removeNode"
        @move="onNodeMove"
        @port-drag-start="onPortDragStart"
        @port-drop="onPortDrop"
      />
    </div>

    <!-- 空画布提示 -->
    <div v-if="canvasStore.nodes.length === 0" class="canvas-empty-hint">
      点击工具栏"添加节点"，将能力拖入画布
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'
import CanvasNode from './CanvasNode.vue'
import CanvasEdge from './CanvasEdge.vue'

const canvasStore = useCanvasStore()
const canvasRef = ref(null)

// ── 节点查找 Map ──
const nodeMap = computed(() => {
  const map = {}
  for (const n of canvasStore.nodes) {
    map[n.id] = n
  }
  return map
})

// ── 画布变换 ──
const transformStyle = computed(() => ({
  transform: `translate(${canvasStore.panX}px, ${canvasStore.panY}px) scale(${canvasStore.zoom})`,
  transformOrigin: '0 0',
}))

// ── 画布平移 ──
let panning = false
let panStartX = 0
let panStartY = 0
let panOrigX = 0
let panOrigY = 0

function onCanvasMouseDown(e) {
  // 只在画布空白区域平移
  if (e.target === canvasRef.value || e.target.classList.contains('canvas-transform') || e.target.classList.contains('canvas-svg')) {
    panning = true
    panStartX = e.clientX
    panStartY = e.clientY
    panOrigX = canvasStore.panX
    panOrigY = canvasStore.panY
    canvasStore.selectNode(null)
  }
}

function onCanvasMouseMove(e) {
  if (panning) {
    canvasStore.setPan(
      panOrigX + (e.clientX - panStartX),
      panOrigY + (e.clientY - panStartY)
    )
  }
  if (draggingEdge.value) {
    updateDraggingEdge(e)
  }
}

function onCanvasMouseUp() {
  panning = false
  if (draggingEdge.value) {
    draggingEdge.value = null
  }
}

// ── 缩放 ──
function onWheel(e) {
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  canvasStore.setZoom(canvasStore.zoom + delta)
}

// ── 节点拖拽 ──
function onNodeMove({ nodeId, x, y }) {
  canvasStore.moveNode(nodeId, x, y)
}

// ── 端口连线拖拽 ──
const draggingEdge = ref(null)
const draggingEdgePath = ref('')

function onPortDragStart({ nodeId, type, event }) {
  draggingEdge.value = { nodeId, type, startX: event.clientX, startY: event.clientY }
}

function updateDraggingEdge(e) {
  if (!draggingEdge.value || !canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const node = nodeMap.value[draggingEdge.value.nodeId]
  if (!node) return

  const nodeWidth = 180
  const nodeHeight = 48

  let x1, y1
  if (draggingEdge.value.type === 'out') {
    x1 = node.x + nodeWidth + 6
    y1 = node.y + nodeHeight / 2
  } else {
    x1 = node.x - 6
    y1 = node.y + nodeHeight / 2
  }

  const x2 = (e.clientX - rect.left - canvasStore.panX) / canvasStore.zoom
  const y2 = (e.clientY - rect.top - canvasStore.panY) / canvasStore.zoom

  const dx = Math.abs(x2 - x1) * 0.5
  draggingEdgePath.value = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

function onPortDrop({ nodeId, type }) {
  if (!draggingEdge.value) return

  const fromInfo = draggingEdge.value
  draggingEdge.value = null
  draggingEdgePath.value = ''

  // out → in
  if (fromInfo.type === 'out' && type === 'in') {
    canvasStore.addEdge(fromInfo.nodeId, nodeId)
  }
  // in → out (反向)
  if (fromInfo.type === 'in' && type === 'out') {
    canvasStore.addEdge(nodeId, fromInfo.nodeId)
  }
}
</script>

<style scoped>
.workflow-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle, var(--border) 1px, transparent 1px);
  background-size: 20px 20px;
  cursor: grab;
  min-height: 0;
}

.workflow-canvas:active {
  cursor: grabbing;
}

.canvas-transform {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.canvas-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}

.canvas-svg :deep(g) {
  pointer-events: auto;
}

.dragging-edge {
  fill: none;
  stroke: var(--accent);
  stroke-width: 2;
  stroke-dasharray: 6 3;
  pointer-events: none;
}

.canvas-empty-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--muted);
  font-size: 14px;
  pointer-events: none;
}
</style>
