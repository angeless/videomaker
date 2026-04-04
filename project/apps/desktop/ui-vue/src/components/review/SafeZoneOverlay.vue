<template>
  <div class="safe-zone-overlay" v-if="ratio">
    <div class="sz-guide" :style="guideStyle">
      <span class="sz-label">{{ ratio }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  ratio: { type: String, default: null }, // '9:16' | '16:9' | '1:1' | '4:5'
})

const guideStyle = computed(() => {
  if (!props.ratio) return {}

  const [w, h] = props.ratio.split(':').map(Number)
  const aspect = w / h

  // Calculate box dimensions as percentage of container
  // The guide shows the "safe" area centered within the video viewport
  if (aspect >= 1) {
    // Landscape or square: width=100%, height by ratio
    return {
      width: '100%',
      height: `${(1 / aspect) * 100}%`,
      maxHeight: '100%',
    }
  } else {
    // Portrait: height=100%, width by ratio
    return {
      height: '100%',
      width: `${aspect * 100}%`,
      maxWidth: '100%',
    }
  }
})
</script>

<style scoped>
.safe-zone-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 5;
}

.sz-guide {
  border: 2px dashed rgba(255, 255, 255, 0.4);
  border-radius: 2px;
  position: relative;
}

.sz-label {
  position: absolute;
  top: -18px;
  left: 4px;
  font-size: 0.6rem;
  color: rgba(255, 255, 255, 0.5);
  background: rgba(0, 0, 0, 0.5);
  padding: 1px 4px;
  border-radius: 2px;
}
</style>
