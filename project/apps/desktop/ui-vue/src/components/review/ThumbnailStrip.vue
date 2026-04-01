<template>
  <div class="thumbnail-strip" v-if="store.thumbnailData">
    <div
      class="ts-frame"
      v-for="(frame, idx) in frames"
      :key="idx"
      :style="frameStyle(frame, idx)"
    ></div>
  </div>
  <div class="thumbnail-strip ts-empty" v-else>
    <span class="ts-placeholder">缩略图加载中…</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()

const props = defineProps({
  pxPerSec: { type: Number, required: true },
})

const frames = computed(() => {
  const td = store.thumbnailData
  if (!td) return []
  const result = []
  for (let i = 0; i < td.frame_count; i++) {
    const col = i % td.columns
    const row = Math.floor(i / td.columns)
    result.push({
      index: i,
      spriteX: col * td.frame_width,
      spriteY: row * td.frame_height,
      timeMs: i * td.interval_ms,
    })
  }
  return result
})

function frameStyle(frame, idx) {
  const td = store.thumbnailData
  if (!td) return {}
  const x = (frame.timeMs / 1000) * props.pxPerSec
  const displayWidth = (td.interval_ms / 1000) * props.pxPerSec
  return {
    left: x + 'px',
    width: Math.max(2, displayWidth) + 'px',
    height: '40px',
    backgroundImage: `url(/api/file?path=${encodeURIComponent(td.sprite_url)})`,
    backgroundPosition: `-${frame.spriteX}px -${frame.spriteY}px`,
    backgroundSize: `${td.columns * td.frame_width}px auto`,
  }
}
</script>

<style scoped>
.thumbnail-strip {
  position: relative;
  height: 40px;
  width: 100%;
}

.ts-frame {
  position: absolute;
  top: 0;
  background-repeat: no-repeat;
  border-right: 1px solid #222;
}

.ts-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1a1a1a;
}

.ts-placeholder {
  font-size: 0.65rem;
  color: #444;
}
</style>
