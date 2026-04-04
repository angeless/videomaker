<template>
  <div class="annotation-toolbar" v-if="store.mode === 'drawing'">
    <!-- Tool selection -->
    <div class="at-tools">
      <button
        v-for="t in tools"
        :key="t.id"
        class="at-btn"
        :class="{ active: currentTool === t.id }"
        :title="t.label"
        @click="selectTool(t.id)"
      >{{ t.icon }}</button>
    </div>

    <div class="at-sep"></div>

    <!-- Color palette -->
    <div class="at-colors">
      <button
        v-for="c in colors"
        :key="c"
        class="at-color-btn"
        :class="{ active: currentColor === c }"
        :style="{ background: c }"
        @click="currentColor = c"
      ></button>
    </div>

    <div class="at-sep"></div>

    <!-- Line width -->
    <div class="at-width">
      <button
        v-for="w in widths"
        :key="w"
        class="at-btn at-btn-sm"
        :class="{ active: currentWidth === w }"
        @click="currentWidth = w"
      >
        <span class="at-width-dot" :style="{ width: w * 2 + 'px', height: w * 2 + 'px' }"></span>
      </button>
    </div>

    <div class="at-sep"></div>

    <!-- Actions -->
    <button class="at-btn" @click="$emit('undo')" title="撤销 (Cmd+Z)">↩</button>
    <button class="at-btn" @click="$emit('redo')" title="重做 (Cmd+Shift+Z)">↪</button>
    <button class="at-btn" @click="$emit('clear')" title="清除">🗑</button>

    <div class="at-sep"></div>

    <button class="at-btn at-btn-done" @click="store.exitMode()">完成</button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()

const emit = defineEmits(['undo', 'redo', 'clear', 'toolChange', 'colorChange', 'widthChange'])

const tools = [
  { id: 'pen',       icon: '✏️', label: '画笔' },
  { id: 'arrow',     icon: '➡️', label: '箭头' },
  { id: 'rect',      icon: '⬜', label: '矩形' },
  { id: 'circle',    icon: '⭕', label: '圆形' },
  { id: 'text',      icon: 'T',  label: '文字标注' },
  { id: 'spotlight', icon: '🔦', label: '聚光灯' },
  { id: 'blur',      icon: '▦',  label: '模糊遮盖' },
  { id: 'eraser',    icon: '🧹', label: '橡皮擦' },
]

const colors = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#a855f7', '#ffffff']
const widths = [2, 3, 5, 8]

const currentTool = ref('pen')
const currentColor = ref('#ef4444')
const currentWidth = ref(3)

function selectTool(id) {
  currentTool.value = id
  emit('toolChange', id)
}

watch(currentColor, (c) => emit('colorChange', c))
watch(currentWidth, (w) => emit('widthChange', w))

defineExpose({ currentTool, currentColor, currentWidth })
</script>

<style scoped>
.annotation-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(0, 0, 0, 0.85);
  padding: 4px 8px;
  border-radius: 8px;
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 20;
}

.at-tools {
  display: flex;
  gap: 2px;
}

.at-btn {
  background: none;
  border: none;
  color: #ccc;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 0.8rem;
}

.at-btn:hover {
  background: #333;
}

.at-btn.active {
  background: #3b82f6;
  color: #fff;
}

.at-btn-sm {
  padding: 4px 6px;
}

.at-btn-done {
  background: #22c55e;
  color: #fff;
  font-size: 0.7rem;
  padding: 4px 10px;
}

.at-btn-done:hover {
  background: #16a34a;
}

.at-sep {
  width: 1px;
  height: 20px;
  background: #444;
  margin: 0 2px;
}

.at-colors {
  display: flex;
  gap: 3px;
}

.at-color-btn {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  padding: 0;
}

.at-color-btn.active {
  border-color: #fff;
}

.at-width {
  display: flex;
  gap: 2px;
  align-items: center;
}

.at-width-dot {
  display: block;
  background: #ccc;
  border-radius: 50%;
}
</style>
