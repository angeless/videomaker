<template>
  <div ref="wrapperRef" class="stepper-wrapper" :class="{ 'has-overflow': hasOverflow }">
    <div ref="stepperRef" class="stepper">
      <template v-for="(label, i) in steps" :key="i">
        <div
          class="stepper-step"
          :class="{
            active: (i + 1) === active,
            completed: (i + 1) < current,
            disabled: (i + 1) > current,
          }"
          :title="(i + 1) < current ? '点击回到此步骤' : (i + 1) > current ? '尚未解锁' : ''"
          @click="(i + 1) <= current ? $emit('select', i + 1) : null"
        >
          <div class="stepper-num">
            <span v-if="(i + 1) < current">✓</span>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span class="stepper-label">{{ label }}</span>
        </div>
        <div
          v-if="i < steps.length - 1"
          class="stepper-connector"
          :class="{ completed: (i + 1) < current }"
        ></div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

defineProps({
  steps: { type: Array, required: true },
  current: { type: Number, default: 1 },
  active: { type: Number, default: 1 },
})

defineEmits(['select'])

const wrapperRef = ref(null)
const stepperRef = ref(null)
const hasOverflow = ref(false)

function checkOverflow() {
  if (!stepperRef.value || !wrapperRef.value) return
  hasOverflow.value = stepperRef.value.scrollWidth > wrapperRef.value.clientWidth
}

let ro = null
onMounted(() => {
  checkOverflow()
  // 监听容器尺寸变化
  if (window.ResizeObserver && wrapperRef.value) {
    ro = new ResizeObserver(checkOverflow)
    ro.observe(wrapperRef.value)
  }
  // 滚动到末尾时隐藏渐变
  stepperRef.value?.addEventListener('scroll', handleScroll)
})

onUnmounted(() => {
  ro?.disconnect()
  stepperRef.value?.removeEventListener('scroll', handleScroll)
})

function handleScroll() {
  if (!stepperRef.value) return
  const el = stepperRef.value
  const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 4
  hasOverflow.value = !atEnd && el.scrollWidth > el.clientWidth
}
</script>
