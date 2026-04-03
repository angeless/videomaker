<template>
  <div class="subtitle-editor" v-if="subtitles.length" ref="trackRef">
    <div
      v-for="(sub, idx) in subtitles"
      :key="sub.id || idx"
      class="se-block"
      :class="{ active: isActive(sub), editing: editingIdx === idx }"
      :style="blockStyle(sub)"
      @click.stop="$emit('seek', sub.start_ms)"
      @dblclick.stop="startEdit(idx)"
      @mousedown.stop="onBlockMouseDown($event, idx)"
      @contextmenu.prevent="openMenu($event, idx)"
    >
      <div
        class="se-handle se-handle-left"
        @mousedown.stop="onHandleMouseDown($event, idx, 'left')"
      ></div>
      <input
        v-if="editingIdx === idx"
        ref="editInput"
        class="se-input"
        v-model="editText"
        @blur="commitEdit"
        @keydown.enter="commitEdit"
        @keydown.escape="cancelEdit"
        @click.stop
      />
      <span v-else class="se-text">{{ sub.text }}</span>
      <div
        class="se-handle se-handle-right"
        @mousedown.stop="onHandleMouseDown($event, idx, 'right')"
      ></div>
    </div>

    <!-- Context menu -->
    <div
      v-if="menuVisible"
      class="se-menu"
      :style="{ left: menuX + 'px', top: menuY + 'px' }"
    >
      <button @click="menuAction('delete')">删除</button>
      <button @click="menuAction('split')">拆分</button>
      <button @click="menuAction('merge')" :disabled="menuIdx >= subtitles.length - 1">合并</button>
    </div>
  </div>
  <div class="subtitle-editor se-empty" v-else>
    <span class="se-placeholder">无字幕数据</span>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()
const trackRef = ref(null)

const props = defineProps({
  pxPerSec: { type: Number, required: true },
  subtitles: { type: Array, default: () => [] },
})

const emit = defineEmits(['seek', 'update:subtitles'])

// ── Inline editing ──
const editingIdx = ref(-1)
const editText = ref('')
const editInput = ref(null)

function startEdit(idx) {
  editingIdx.value = idx
  editText.value = props.subtitles[idx].text
  nextTick(() => {
    if (editInput.value) {
      const el = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value
      if (el) el.focus()
    }
  })
}

function commitEdit() {
  if (editingIdx.value < 0) return
  const updated = [...props.subtitles]
  updated[editingIdx.value] = { ...updated[editingIdx.value], text: editText.value }
  emit('update:subtitles', updated)
  editingIdx.value = -1
}

function cancelEdit() {
  editingIdx.value = -1
}

// ── Drag to move / resize ──
let dragState = null

function onBlockMouseDown(e, idx) {
  if (editingIdx.value === idx) return
  dragState = { idx, mode: 'move', startX: e.clientX, origStart: props.subtitles[idx].start_ms, origEnd: props.subtitles[idx].end_ms }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function onHandleMouseDown(e, idx, side) {
  dragState = { idx, mode: side, startX: e.clientX, origStart: props.subtitles[idx].start_ms, origEnd: props.subtitles[idx].end_ms }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function onDragMove(e) {
  if (!dragState) return
  const dx = e.clientX - dragState.startX
  const dtMs = (dx / props.pxPerSec) * 1000

  const updated = [...props.subtitles]
  const sub = { ...updated[dragState.idx] }

  if (dragState.mode === 'move') {
    sub.start_ms = Math.max(0, Math.round(dragState.origStart + dtMs))
    sub.end_ms = Math.max(sub.start_ms + 100, Math.round(dragState.origEnd + dtMs))
  } else if (dragState.mode === 'left') {
    sub.start_ms = Math.max(0, Math.min(sub.end_ms - 100, Math.round(dragState.origStart + dtMs)))
  } else if (dragState.mode === 'right') {
    sub.end_ms = Math.max(sub.start_ms + 100, Math.round(dragState.origEnd + dtMs))
  }

  updated[dragState.idx] = sub
  emit('update:subtitles', updated)
}

function onDragEnd() {
  dragState = null
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
}

// ── Context menu ──
const menuVisible = ref(false)
const menuX = ref(0)
const menuY = ref(0)
const menuIdx = ref(-1)

function openMenu(e, idx) {
  menuIdx.value = idx
  menuX.value = e.offsetX
  menuY.value = e.offsetY
  menuVisible.value = true
}

function closeMenu() {
  menuVisible.value = false
  menuIdx.value = -1
}

function menuAction(action) {
  const idx = menuIdx.value
  const updated = [...props.subtitles]

  if (action === 'delete') {
    updated.splice(idx, 1)
  } else if (action === 'split') {
    const sub = updated[idx]
    const mid = Math.round((sub.start_ms + sub.end_ms) / 2)
    const first = { ...sub, end_ms: mid, text: sub.text }
    const second = { ...sub, start_ms: mid, id: undefined }
    updated.splice(idx, 1, first, second)
  } else if (action === 'merge' && idx < updated.length - 1) {
    const a = updated[idx]
    const b = updated[idx + 1]
    const merged = { ...a, end_ms: b.end_ms, text: a.text + b.text }
    updated.splice(idx, 2, merged)
  }

  emit('update:subtitles', updated)
  closeMenu()
}

function onDocClick() { closeMenu() }
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))

// ── Helpers ──
function blockStyle(sub) {
  const x = (sub.start_ms / 1000) * props.pxPerSec
  const w = ((sub.end_ms - sub.start_ms) / 1000) * props.pxPerSec
  return {
    left: x + 'px',
    width: Math.max(4, w) + 'px',
  }
}

function isActive(sub) {
  const t = store.currentTimeMs
  return t >= sub.start_ms && t <= sub.end_ms
}
</script>

<style scoped>
.subtitle-editor {
  position: relative;
  height: 24px;
  width: 100%;
}

.se-block {
  position: absolute;
  top: 2px;
  height: 20px;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 3px;
  display: flex;
  align-items: center;
  padding: 0 4px;
  cursor: grab;
  overflow: hidden;
  transition: background 0.15s;
}

.se-block:hover {
  background: #333;
}

.se-block.active {
  background: #1e3a5f;
  border-color: #3b82f6;
}

.se-block.editing {
  overflow: visible;
  z-index: 5;
}

.se-handle {
  position: absolute;
  top: 0;
  width: 5px;
  height: 100%;
  cursor: ew-resize;
  z-index: 2;
}

.se-handle-left { left: 0; }
.se-handle-right { right: 0; }

.se-handle:hover {
  background: rgba(59, 130, 246, 0.4);
}

.se-text {
  font-size: 0.55rem;
  color: #ccc;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.se-input {
  font-size: 0.55rem;
  color: #fff;
  background: #111;
  border: 1px solid #3b82f6;
  border-radius: 2px;
  padding: 0 2px;
  width: 100%;
  outline: none;
}

.se-menu {
  position: absolute;
  background: #1a1a1a;
  border: 1px solid #444;
  border-radius: 4px;
  z-index: 30;
  overflow: hidden;
}

.se-menu button {
  display: block;
  width: 100%;
  padding: 4px 12px;
  background: none;
  border: none;
  color: #ccc;
  font-size: 0.65rem;
  cursor: pointer;
  text-align: left;
}

.se-menu button:hover {
  background: #333;
}

.se-menu button:disabled {
  color: #555;
  cursor: default;
}

.se-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  background: #111;
}

.se-placeholder {
  font-size: 0.6rem;
  color: #444;
}
</style>
