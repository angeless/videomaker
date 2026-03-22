<template>
  <div
    class="tl-clip-block"
    :class="[statusClass, { 'tl-clip-selected': isSelected, 'tl-clip-face': clip.has_face, 'tl-clip-drag-over': isDragOver }]"
    :style="style"
    :title="tooltip"
    draggable="true"
    @click.stop="onClick"
    @dragstart="onDragStart"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
    @dragend="onDragEnd"
  >
    <span v-if="showLabel" class="tl-clip-label">
      #{{ clip.clip_index }}
      <span v-if="showDesc" class="tl-clip-desc">{{ clip.scene_description }}</span>
    </span>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useTimelineStore } from '../../stores/timeline.js'
import { useTimeline } from '../../composables/useTimeline.js'
import { useFormatters } from '../../composables/useFormatters.js'

const props = defineProps({
  clip: { type: Object, required: true },
})

const store = useTimelineStore()
const { clipStyle } = useTimeline()
const { formatDuration } = useFormatters()

const style = computed(() => clipStyle(props.clip))
const isSelected = computed(() => store.selectedClipIndex === props.clip.clip_index)

const widthNum = computed(() => parseFloat(style.value.width) || 0)
const showLabel = computed(() => widthNum.value > 30)
const showDesc = computed(() => widthNum.value > 100)

const statusClass = computed(() => {
  const s = props.clip.processing_status
  if (s === 'rendered') return 'tl-clip-rendered'
  if (s === 'matched') return 'tl-clip-matched'
  return 'tl-clip-pending'
})

const tooltip = computed(() => {
  const c = props.clip
  return `#${c.clip_index} ${c.filename || c.video_id || ''} (${formatDuration(c.duration)})${c.has_face ? ' [人脸]' : ''}`
})

const isDragOver = ref(false)

function onClick() {
  store.selectClip(props.clip.clip_index)
}

function onDragStart(e) {
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(clipArrayIndex.value))
}

function onDragOver() {
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(e) {
  isDragOver.value = false
  const fromStr = e.dataTransfer.getData('text/plain')
  const fromIdx = parseInt(fromStr, 10)
  if (Number.isNaN(fromIdx) || fromIdx === clipArrayIndex.value) return
  store.reorderClips(fromIdx, clipArrayIndex.value)
}

function onDragEnd() {
  isDragOver.value = false
}

const clipArrayIndex = computed(() => {
  return store.clips.findIndex(c => c.clip_index === props.clip.clip_index)
})
</script>

<style scoped>
.tl-clip-block {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: 4px;
  cursor: pointer;
  overflow: hidden;
  display: flex;
  align-items: center;
  padding: 0 4px;
  transition: outline 0.1s;
  box-sizing: border-box;
}

.tl-clip-pending {
  background: var(--surface2);
  border: 1px dashed var(--muted);
}

.tl-clip-matched {
  background: rgba(90, 141, 238, 0.25);
  border: 1px solid var(--accent);
}

.tl-clip-rendered {
  background: rgba(52, 211, 153, 0.2);
  border: 1px solid var(--success);
}

.tl-clip-face {
  border-left: 3px solid var(--warn);
}

.tl-clip-selected {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.tl-clip-drag-over {
  outline: 2px dashed var(--warn);
  outline-offset: 1px;
}

.tl-clip-label {
  font-size: 10px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}

.tl-clip-desc {
  color: var(--muted);
  margin-left: 4px;
}
</style>
