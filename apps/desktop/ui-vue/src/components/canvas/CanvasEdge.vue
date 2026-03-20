<template>
  <g class="canvas-edge" :class="{ selected: isSelected }" @click.stop="onClick">
    <path :d="pathD" class="edge-path" />
    <path :d="pathD" class="edge-hit-area" />
    <!-- Delete button at midpoint -->
    <g v-if="isSelected" :transform="`translate(${midX}, ${midY})`">
      <circle r="10" class="edge-delete-bg" @click.stop="onDelete" />
      <text class="edge-delete-icon" text-anchor="middle" dominant-baseline="central" @click.stop="onDelete">✕</text>
    </g>
  </g>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'

const props = defineProps({
  edge: { type: Object, required: true },
})

const canvas = useCanvasStore()

const fromNode = computed(() => canvas.nodes.find(n => n.id === props.edge.from))
const toNode = computed(() => canvas.nodes.find(n => n.id === props.edge.to))
const isSelected = computed(() => canvas.selectedEdgeId === props.edge.id)

const sourceX = computed(() => fromNode.value ? fromNode.value.x + fromNode.value.width / 2 : 0)
const sourceY = computed(() => fromNode.value ? fromNode.value.y + (fromNode.value.height || 72) + 6 : 0)
const targetX = computed(() => toNode.value ? toNode.value.x + toNode.value.width / 2 : 0)
const targetY = computed(() => toNode.value ? toNode.value.y - 6 : 0)

const pathD = computed(() => {
  const sx = sourceX.value, sy = sourceY.value
  const tx = targetX.value, ty = targetY.value
  const dy = Math.abs(ty - sy)
  const cp = Math.max(40, dy * 0.4)
  return `M ${sx},${sy} C ${sx},${sy + cp} ${tx},${ty - cp} ${tx},${ty}`
})

const midX = computed(() => (sourceX.value + targetX.value) / 2)
const midY = computed(() => (sourceY.value + targetY.value) / 2)

function onClick() {
  canvas.selectEdge(props.edge.id)
}

function onDelete() {
  canvas.removeEdge(props.edge.id)
}
</script>

<style scoped>
.edge-path {
  fill: none;
  stroke: var(--accent, #5a8dee);
  stroke-width: 2;
  opacity: 0.6;
  transition: opacity 0.15s, stroke-width 0.15s;
}

.canvas-edge:hover .edge-path,
.canvas-edge.selected .edge-path {
  opacity: 1;
  stroke-width: 2.5;
}

.edge-hit-area {
  fill: none;
  stroke: transparent;
  stroke-width: 16;
  cursor: pointer;
}

.edge-delete-bg {
  fill: var(--danger, #f87171);
  cursor: pointer;
  opacity: 0.9;
}

.edge-delete-bg:hover {
  opacity: 1;
}

.edge-delete-icon {
  fill: #fff;
  font-size: 10px;
  cursor: pointer;
  pointer-events: none;
}
</style>
