<template>
  <div class="tl-track tl-track-subs" :style="{ width: totalWidth + 'px' }">
    <div class="tl-track-label">{{ labels.timeline.subtitleTrack }}</div>
    <div class="tl-track-content" :style="{ width: totalWidth + 'px' }">
      <div
        v-for="(sub, i) in store.subtitles"
        :key="i"
        class="tl-sub-block"
        :style="subtitleStyle(sub)"
        :title="sub.cn_text || sub.en_text || ''"
      >
        <span class="tl-sub-text">{{ sub.cn_text || sub.en_text || '' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useTimelineStore } from '../../stores/timeline.js'
import { useTimeline } from '../../composables/useTimeline.js'
import labels from '../../i18n/labels.js'

const store = useTimelineStore()
const { totalWidth, subtitleStyle } = useTimeline()
</script>

<style scoped>
.tl-track {
  display: flex;
  align-items: stretch;
  min-height: 28px;
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
  min-height: 28px;
}

.tl-sub-block {
  position: absolute;
  top: 2px;
  bottom: 2px;
  background: rgba(139, 92, 246, 0.2);
  border: 1px solid rgba(139, 92, 246, 0.4);
  border-radius: 3px;
  overflow: hidden;
  display: flex;
  align-items: center;
  padding: 0 4px;
}

.tl-sub-text {
  font-size: 9px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
