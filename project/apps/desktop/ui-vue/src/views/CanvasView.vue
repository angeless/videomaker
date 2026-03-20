<template>
  <div class="canvas-view">
    <CanvasToolbar />
    <div class="canvas-main">
      <NodePalette />
      <CanvasBoard />
      <NodePropsPanel />
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useCanvasStore } from '../stores/canvas.js'
import CanvasToolbar from '../components/canvas/CanvasToolbar.vue'
import NodePalette from '../components/canvas/NodePalette.vue'
import CanvasBoard from '../components/canvas/CanvasBoard.vue'
import NodePropsPanel from '../components/canvas/NodePropsPanel.vue'

const route = useRoute()
const canvas = useCanvasStore()

onMounted(() => {
  // Load existing workflow if ?wf=<id> is in query
  const wfId = route.query.wf
  if (wfId && wfId !== canvas.workflowId) {
    canvas.loadFromBackend(wfId)
  }
})
</script>

<style scoped>
.canvas-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.canvas-main {
  flex: 1;
  display: flex;
  min-height: 0;
}
</style>
