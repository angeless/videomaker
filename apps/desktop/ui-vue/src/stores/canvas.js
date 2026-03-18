import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'
import { useToastStore } from './toast.js'

let _nextId = 1

export const useCanvasStore = defineStore('canvas', () => {
  const api = useApiStore()
  const toast = useToastStore()

  // ── State ──
  const nodes = ref([])
  const edges = ref([])
  const viewport = ref({ panX: 0, panY: 0, zoom: 1 })
  const selectedNodeId = ref('')
  const selectedEdgeId = ref('')
  const workflowId = ref('')
  const workflowName = ref('新工作流')
  const dirty = ref(false)
  const saving = ref(false)
  const running = ref(false)

  // ── Computed ──
  const nodeCount = computed(() => nodes.value.length)
  const edgeCount = computed(() => edges.value.length)

  // ── Node CRUD ──
  function addNode(capabilityId, label, x, y) {
    const id = `node_${Date.now()}_${_nextId++}`
    nodes.value.push({ id, capability_id: capabilityId, label, x: snap(x), y: snap(y), width: 180, height: 72 })
    dirty.value = true
    return id
  }

  function removeNode(id) {
    nodes.value = nodes.value.filter(n => n.id !== id)
    edges.value = edges.value.filter(e => e.from !== id && e.to !== id)
    if (selectedNodeId.value === id) selectedNodeId.value = ''
    dirty.value = true
  }

  function duplicateNode(id) {
    const src = nodes.value.find(n => n.id === id)
    if (!src) return ''
    return addNode(src.capability_id, src.label, src.x + 40, src.y + 40)
  }

  function disconnectNode(id) {
    edges.value = edges.value.filter(e => e.from !== id && e.to !== id)
    dirty.value = true
  }

  const GRID = 24

  function snap(v) { return Math.round(v / GRID) * GRID }

  function moveNode(id, x, y) {
    const node = nodes.value.find(n => n.id === id)
    if (node) { node.x = snap(x); node.y = snap(y); dirty.value = true }
  }

  // ── Edge CRUD ──
  function addEdge(fromId, toId) {
    if (fromId === toId) return
    if (edges.value.some(e => e.from === fromId && e.to === toId)) return
    // Only one output per node
    edges.value = edges.value.filter(e => e.from !== fromId)
    const id = `edge_${Date.now()}_${_nextId++}`
    edges.value.push({ id, from: fromId, to: toId })
    dirty.value = true
  }

  function removeEdge(id) {
    edges.value = edges.value.filter(e => e.id !== id)
    if (selectedEdgeId.value === id) selectedEdgeId.value = ''
    dirty.value = true
  }

  // ── Selection ──
  function selectNode(id) {
    selectedNodeId.value = id
    selectedEdgeId.value = ''
  }

  function selectEdge(id) {
    selectedEdgeId.value = id
    selectedNodeId.value = ''
  }

  function clearSelection() {
    selectedNodeId.value = ''
    selectedEdgeId.value = ''
  }

  function deleteSelected() {
    if (selectedNodeId.value) removeNode(selectedNodeId.value)
    else if (selectedEdgeId.value) removeEdge(selectedEdgeId.value)
  }

  // ── Viewport ──
  function pan(dx, dy) {
    viewport.value.panX += dx
    viewport.value.panY += dy
  }

  function zoomAt(delta, cx, cy) {
    const old = viewport.value.zoom
    const next = Math.max(0.25, Math.min(2, old + delta))
    const ratio = next / old
    viewport.value.panX = cx - ratio * (cx - viewport.value.panX)
    viewport.value.panY = cy - ratio * (cy - viewport.value.panY)
    viewport.value.zoom = next
  }

  function resetView() {
    viewport.value = { panX: 60, panY: 60, zoom: 1 }
  }

  // ── Clear ──
  function clear() {
    nodes.value = []
    edges.value = []
    selectedNodeId.value = ''
    selectedEdgeId.value = ''
    workflowId.value = ''
    workflowName.value = '新工作流'
    dirty.value = false
    resetView()
  }

  // ── Persistence ──
  function toSteps() {
    return nodes.value.map((node, i) => {
      const outEdge = edges.value.find(e => e.from === node.id)
      return {
        step_id: node.id,
        index: i + 1,
        capability_id: node.capability_id,
        name: node.label,
        node_type: 'action',
        action: 'auto',
        input: { _canvas: { x: node.x, y: node.y } },
        next_step_id: outEdge?.to || '',
      }
    })
  }

  async function saveToBackend() {
    saving.value = true
    const payload = {
      name: workflowName.value,
      steps: toSteps(),
    }
    let data
    if (workflowId.value) {
      data = await api.api('PUT', `/api/workflows/${workflowId.value}`, payload)
    } else {
      data = await api.api('POST', '/api/workflows', payload)
    }
    saving.value = false
    if (data.error) {
      toast.show('保存失败: ' + data.error, 'danger')
      return false
    }
    if (data.workflow_id) workflowId.value = data.workflow_id
    dirty.value = false
    toast.show('工作流已保存', 'success')
    return true
  }

  async function loadFromBackend(wfId) {
    const data = await api.api('GET', `/api/workflows/${wfId}?include_steps=true`)
    if (data.error) {
      toast.show('加载失败: ' + data.error, 'danger')
      return false
    }
    const wf = data.workflow || data
    clear()
    workflowId.value = wfId
    workflowName.value = wf.name || wfId

    const steps = wf.steps || []
    // Restore nodes with canvas positions or auto-layout
    steps.forEach((step, i) => {
      const pos = step.input?._canvas || {}
      nodes.value.push({
        id: step.step_id || `step_${i}`,
        capability_id: step.capability_id || '',
        label: step.name || step.capability_id || `步骤 ${i + 1}`,
        x: pos.x ?? 100,
        y: pos.y ?? (80 + i * 120),
        width: 180,
        height: 72,
      })
    })
    // Restore edges from next_step_id
    steps.forEach(step => {
      if (step.next_step_id) {
        const fromId = step.step_id || ''
        const toId = step.next_step_id
        if (nodes.value.some(n => n.id === fromId) && nodes.value.some(n => n.id === toId)) {
          edges.value.push({ id: `edge_${fromId}_${toId}`, from: fromId, to: toId })
        }
      }
    })
    dirty.value = false
    return true
  }

  async function runWorkflow() {
    if (!workflowId.value) {
      toast.show('请先保存工作流', 'warn')
      return
    }
    running.value = true
    const data = await api.api('POST', `/api/workflows/${workflowId.value}/run`)
    running.value = false
    if (data.error) {
      toast.show('运行失败: ' + data.error, 'danger')
      return
    }
    toast.show('工作流已启动运行', 'success')
  }

  return {
    nodes, edges, viewport, selectedNodeId, selectedEdgeId,
    workflowId, workflowName, dirty, saving, running,
    nodeCount, edgeCount,
    GRID, snap,
    addNode, removeNode, duplicateNode, disconnectNode, moveNode,
    addEdge, removeEdge,
    selectNode, selectEdge, clearSelection, deleteSelected,
    pan, zoomAt, resetView, clear,
    toSteps, saveToBackend, loadFromBackend, runWorkflow,
  }
})
