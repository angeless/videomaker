<template>
  <div
    class="canvas-node"
    :class="{ selected: isSelected }"
    :style="nodeStyle"
    @mousedown.stop="onMouseDown"
    @click.stop="onClick"
  >
    <!-- Input port (top) -->
    <div
      class="port port-in"
      @mousedown.stop
      @mouseup.stop="$emit('port-drop', node.id)"
    ></div>

    <div class="node-body">
      <span class="node-icon">{{ icon }}</span>
      <div class="node-info">
        <div class="node-label">{{ node.label }}</div>
        <div class="node-cap">{{ node.capability_id }}</div>
      </div>
    </div>

    <!-- Output port (bottom) -->
    <div
      class="port port-out"
      @mousedown.stop="$emit('port-drag-start', node.id)"
    ></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '../../stores/canvas.js'

const props = defineProps({
  node: { type: Object, required: true },
})

const emit = defineEmits(['port-drag-start', 'port-drop'])

const canvas = useCanvasStore()

const icons = {
  topic_library: '💡', topic_copy: '📝', article_expand: '📰',
  text_rough: '✂️', short_clip: '⚡', refinement: '✨',
  audio_voice: '🎵', subtitle_calibration: '📋', image_semantic: '🖼️',
  publish_prep: '📤', social_export: '🌐', content_publish: '🚀',
}

const icon = computed(() => icons[props.node.capability_id] || '🔧')
const isSelected = computed(() => canvas.selectedNodeId === props.node.id)

const nodeStyle = computed(() => ({
  left: `${props.node.x}px`,
  top: `${props.node.y}px`,
  width: `${props.node.width}px`,
}))

function onClick() {
  canvas.selectNode(props.node.id)
}

let dragStartX = 0
let dragStartY = 0
let nodeStartX = 0
let nodeStartY = 0

function onMouseDown(e) {
  if (e.target.classList.contains('port') || e.target.classList.contains('port-in') || e.target.classList.contains('port-out')) return
  canvas.selectNode(props.node.id)
  dragStartX = e.clientX
  dragStartY = e.clientY
  nodeStartX = props.node.x
  nodeStartY = props.node.y
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e) {
  const zoom = canvas.viewport.zoom
  const dx = (e.clientX - dragStartX) / zoom
  const dy = (e.clientY - dragStartY) / zoom
  canvas.moveNode(props.node.id, nodeStartX + dx, nodeStartY + dy)
}

function onMouseUp() {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
}
</script>

<style scoped>
.canvas-node {
  position: absolute;
  background: var(--surface, #1a1a2e);
  border: 1.5px solid var(--border, #333);
  border-radius: 10px;
  cursor: grab;
  user-select: none;
  transition: box-shadow 0.15s, border-color 0.15s;
}

.canvas-node:hover {
  border-color: var(--accent, #5a8dee);
  box-shadow: 0 2px 12px rgba(90, 141, 238, 0.15);
}

.canvas-node.selected {
  border-color: var(--accent, #5a8dee);
  box-shadow: 0 0 0 2px rgba(90, 141, 238, 0.3), 0 4px 16px rgba(90, 141, 238, 0.2);
}

.canvas-node:active {
  cursor: grabbing;
}

.node-body {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
}

.node-icon {
  font-size: 22px;
  flex-shrink: 0;
}

.node-info {
  overflow: hidden;
}

.node-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-cap {
  font-size: 10px;
  color: var(--muted, #888);
  margin-top: 2px;
}

/* Ports */
.port {
  position: absolute;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--surface2, #252540);
  border: 2px solid var(--border, #333);
  left: 50%;
  transform: translateX(-50%);
  cursor: crosshair;
  z-index: 2;
  transition: background 0.12s, transform 0.12s;
}

.port:hover {
  background: var(--accent, #5a8dee);
  border-color: var(--accent, #5a8dee);
  transform: translateX(-50%) scale(1.3);
}

.port-in {
  top: -6px;
}

.port-out {
  bottom: -6px;
}
</style>
