<template>
  <div v-if="canvas.nodeCount > 0" class="minimap" @mousedown.stop="onMinimapClick">
    <svg :viewBox="viewBox" class="minimap-svg">
      <!-- Nodes as small rectangles -->
      <rect
        v-for="node in canvas.nodes"
        :key="node.id"
        :x="node.x"
        :y="node.y"
        :width="node.width"
        :height="node.height || 72"
        rx="4"
        class="mm-node"
        :class="{ selected: node.id === canvas.selectedNodeId }"
      />
      <!-- Edges as lines -->
      <line
        v-for="edge in canvas.edges"
        :key="edge.id"
        :x1="edgeCoords(edge).x1"
        :y1="edgeCoords(edge).y1"
        :x2="edgeCoords(edge).x2"
        :y2="edgeCoords(edge).y2"
        class="mm-edge"
      />
      <!-- Viewport rectangle -->
      <rect
        :x="vpRect.x"
        :y="vpRect.y"
        :width="vpRect.w"
        :height="vpRect.h"
        class="mm-viewport"
      />
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'

const props = defineProps({
  boardWidth: { type: Number, default: 1000 },
  boardHeight: { type: Number, default: 700 },
})

const canvas = useCanvasStore()

// Bounding box of all nodes with padding
const bounds = computed(() => {
  if (canvas.nodes.length === 0) return { x: 0, y: 0, w: 800, h: 600 }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of canvas.nodes) {
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + n.width)
    maxY = Math.max(maxY, n.y + (n.height || 72))
  }
  const pad = 100
  const w = Math.max(800, maxX - minX + pad * 2)
  const h = Math.max(600, maxY - minY + pad * 2)
  return { x: minX - pad, y: minY - pad, w, h }
})

const viewBox = computed(() => {
  const b = bounds.value
  return `${b.x} ${b.y} ${b.w} ${b.h}`
})

// Current viewport rectangle in canvas space
const vpRect = computed(() => {
  const v = canvas.viewport
  const x = -v.panX / v.zoom
  const y = -v.panY / v.zoom
  const w = props.boardWidth / v.zoom
  const h = props.boardHeight / v.zoom
  return { x, y, w, h }
})

function edgeCoords(edge) {
  const from = canvas.nodes.find(n => n.id === edge.from)
  const to = canvas.nodes.find(n => n.id === edge.to)
  if (!from || !to) return { x1: 0, y1: 0, x2: 0, y2: 0 }
  return {
    x1: from.x + from.width / 2,
    y1: from.y + (from.height || 72),
    x2: to.x + to.width / 2,
    y2: to.y,
  }
}

function onMinimapClick(e) {
  const svg = e.currentTarget.querySelector('svg')
  if (!svg) return
  const rect = svg.getBoundingClientRect()
  const b = bounds.value
  // Map click position to canvas coordinates
  const cx = b.x + (e.clientX - rect.left) / rect.width * b.w
  const cy = b.y + (e.clientY - rect.top) / rect.height * b.h
  // Center the viewport on that point
  const v = canvas.viewport
  canvas.viewport.panX = props.boardWidth / 2 - cx * v.zoom
  canvas.viewport.panY = props.boardHeight / 2 - cy * v.zoom
}
</script>

<style scoped>
.minimap {
  position: absolute;
  bottom: 40px;
  right: 12px;
  width: 160px;
  height: 100px;
  background: var(--surface, #1a1a2e);
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  opacity: 0.85;
  transition: opacity 0.15s;
}

.minimap:hover {
  opacity: 1;
}

.minimap-svg {
  width: 100%;
  height: 100%;
}

.mm-node {
  fill: var(--accent, #5a8dee);
  opacity: 0.5;
}

.mm-node.selected {
  opacity: 1;
}

.mm-edge {
  stroke: var(--accent, #5a8dee);
  stroke-width: 2;
  opacity: 0.3;
}

.mm-viewport {
  fill: rgba(255, 255, 255, 0.06);
  stroke: rgba(255, 255, 255, 0.3);
  stroke-width: 2;
  stroke-dasharray: 4 2;
}
</style>
