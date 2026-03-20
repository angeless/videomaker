<template>
  <div class="tl-track tl-track-clips" :style="{ width: totalWidth + 'px' }">
    <div class="tl-track-label">{{ labels.timeline.clipTrack }}</div>
    <div class="tl-track-content" :style="{ width: totalWidth + 'px' }">
      <TimelineClipBlock
        v-for="clip in store.clips"
        :key="clip.clip_index"
        :clip="clip"
      />
    </div>
  </div>
</template>

<script setup>
import { useTimelineStore } from '../../stores/timeline.js'
import { useTimeline } from '../../composables/useTimeline.js'
import labels from '../../i18n/labels.js'
import TimelineClipBlock from './TimelineClipBlock.vue'

const store = useTimelineStore()
const { totalWidth } = useTimeline()
</script>

<style scoped>
.tl-track {
  display: flex;
  align-items: stretch;
  min-height: 40px;
}

.tl-track-label {
  width: 48px;
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted);
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 1px solid var(--border);
  position: sticky;
  left: 0;
  background: var(--surface);
  z-index: 2;
}

.tl-track-content {
  position: relative;
  flex: 1;
  min-height: 40px;
}
</style>
