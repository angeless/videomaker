<template>
  <div v-if="hasAudio" class="tl-track tl-track-audio" :style="{ width: totalWidth + 'px' }">
    <div class="tl-track-label">{{ labels.timeline.audioTrack }}</div>
    <div class="tl-track-content" :style="{ width: totalWidth + 'px' }">
      <div v-if="store.audio.bgm" class="tl-audio-bar tl-audio-bgm" :style="{ width: totalWidth + 'px' }">
        <span class="tl-audio-label">{{ store.audio.bgm.label }} ({{ Math.round((store.audio.bgm.volume || 0.35) * 100) }}%)</span>
      </div>
      <div v-if="store.audio.narration" class="tl-audio-bar tl-audio-narration" :style="{ width: totalWidth + 'px' }">
        <span class="tl-audio-label">{{ store.audio.narration.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useTimelineStore } from '../../stores/timeline.js'
import { useTimeline } from '../../composables/useTimeline.js'
import labels from '../../i18n/labels.js'

const store = useTimelineStore()
const { totalWidth } = useTimeline()

const hasAudio = computed(() => store.audio.bgm || store.audio.narration)
</script>

<style scoped>
.tl-track {
  display: flex;
  align-items: stretch;
  min-height: 24px;
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
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.tl-audio-bar {
  height: 18px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  padding: 0 6px;
}

.tl-audio-bgm {
  background: rgba(52, 211, 153, 0.15);
  border: 1px solid rgba(52, 211, 153, 0.3);
}

.tl-audio-narration {
  background: rgba(251, 191, 36, 0.15);
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.tl-audio-label {
  font-size: 9px;
  color: var(--muted);
  white-space: nowrap;
}
</style>
