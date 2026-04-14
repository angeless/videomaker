<template>
  <div class="timeline-panel" :class="{ collapsed: !store.visible }">
    <!-- 折叠态 -->
    <div class="tl-header" @click="store.toggleVisible()">
      <span class="tl-toggle">{{ store.visible ? '▼' : '▶' }}</span>
      <span class="tl-title">{{ labels.timeline.toggle }}</span>
      <span v-if="store.totalDuration > 0" class="tl-duration text-muted">
        {{ labels.timeline.totalDuration }}：{{ formatDuration(store.totalDuration) }}
      </span>
      <div v-if="store.visible" class="tl-zoom" @click.stop>
        <button class="btn btn-ghost btn-xs" @click="zoomOut" :disabled="store.zoom <= 0.25">−</button>
        <input
          type="range"
          min="0.25" max="4" step="0.25"
          :value="store.zoom"
          @input="store.setZoom(Number($event.target.value))"
          class="tl-zoom-slider"
        />
        <button class="btn btn-ghost btn-xs" @click="zoomIn" :disabled="store.zoom >= 4">+</button>
        <span class="tl-zoom-label text-muted">{{ Math.round(store.zoom * 100) }}%</span>
      </div>
    </div>

    <!-- 展开态 -->
    <div v-if="store.visible" class="tl-body">
      <div v-if="!store.clips.length" class="tl-empty text-muted">
        {{ labels.timeline.noData }}
      </div>
      <template v-else>
        <!-- 选中 clip 详情 -->
        <TimelineClipInfo />

        <!-- 时间轴滚动区域 -->
        <div class="tl-scroll" ref="scrollRef">
          <TimelineRuler />
          <div class="tl-tracks">
            <!-- C6: Multi-track rendering (when multiTracks available) -->
            <template v-if="multiTracks.length > 0">
              <div v-for="track in multiTracks" :key="track.track_id" class="tl-multi-row">
                <TimelineTrackHeader
                  :track="track"
                  @toggle-lock="onToggleLock"
                  @toggle-mute="onToggleMute"
                  @set-volume="onSetVolume"
                />
                <div class="tl-clip-lane">
                  <div
                    v-for="clip in track.clips"
                    :key="clip.clip_id"
                    class="tl-clip-block"
                    :class="{ selected: selectedClipId === clip.clip_id }"
                    :style="clipStyle(clip)"
                    @click="selectedClipId = clip.clip_id"
                  >
                    {{ clip.label || clip.clip_id.slice(0, 6) }}
                  </div>
                </div>
              </div>
            </template>
            <!-- Fallback: legacy 3-track view -->
            <template v-else>
              <TimelineTrackClips />
              <TimelineTrackSubtitles />
              <TimelineTrackAudio />
            </template>
            <TimelinePlayhead :scrollContainer="scrollRef" />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useTimelineStore } from '../../stores/timeline.js'
import { useReviewStore } from '../../stores/review.js'
import { useFormatters } from '../../composables/useFormatters.js'
import labels from '../../i18n/labels.js'
import TimelineRuler from './TimelineRuler.vue'
import TimelinePlayhead from './TimelinePlayhead.vue'
import TimelineTrackClips from './TimelineTrackClips.vue'
import TimelineTrackSubtitles from './TimelineTrackSubtitles.vue'
import TimelineTrackAudio from './TimelineTrackAudio.vue'
import TimelineClipInfo from './TimelineClipInfo.vue'
import TimelineTrackHeader from './TimelineTrackHeader.vue'

const store = useTimelineStore()
const reviewStore = useReviewStore()
const { formatDuration } = useFormatters()
const scrollRef = ref(null)
const multiTracks = ref([])
const selectedClipId = ref(null)

// C6: Load multi-track data from C4 API
async function loadMultiTracks() {
  const sid = reviewStore.sessionId
  if (!sid) return
  try {
    const resp = await fetch(`/api/review/${sid}/timeline`)
    if (resp.ok) {
      const data = await resp.json()
      if (data.success && data.tracks) {
        multiTracks.value = data.tracks
      }
    }
  } catch { /* multi-track API not available, use legacy */ }
}

function clipStyle(clip) {
  const pxPerMs = (store.zoom || 1) * 0.1
  return {
    left: `${clip.start_ms * pxPerMs}px`,
    width: `${Math.max(20, (clip.end_ms - clip.start_ms) * pxPerMs)}px`,
  }
}

async function onToggleLock(trackId) {
  const track = multiTracks.value.find(t => t.track_id === trackId)
  if (!track) return
  const newLocked = !track.locked
  try {
    const resp = await fetch(`/api/review/${reviewStore.sessionId}/timeline/tracks/${trackId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locked: newLocked }),
    })
    if (resp.ok) track.locked = newLocked
  } catch { /* keep local state unchanged on error */ }
}

async function onToggleMute(trackId) {
  const track = multiTracks.value.find(t => t.track_id === trackId)
  if (!track) return
  const newMuted = !track.muted
  try {
    const resp = await fetch(`/api/review/${reviewStore.sessionId}/timeline/tracks/${trackId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ muted: newMuted }),
    })
    if (resp.ok) track.muted = newMuted
  } catch { /* keep local state unchanged on error */ }
}

async function onSetVolume(trackId, vol) {
  const track = multiTracks.value.find(t => t.track_id === trackId)
  if (!track) return
  try {
    const resp = await fetch(`/api/review/${reviewStore.sessionId}/timeline/tracks/${trackId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: vol }),
    })
    if (resp.ok) track.volume = vol
  } catch { /* keep local state unchanged on error */ }
}

function zoomIn() {
  store.setZoom(Math.min(store.zoom + 0.25, 4))
}

function zoomOut() {
  store.setZoom(Math.max(store.zoom - 0.25, 0.25))
}

onMounted(() => {
  if (!store.timelineData) {
    store.loadTimeline()
  }
  loadMultiTracks()
})
</script>

<style scoped>
.timeline-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  margin-top: 16px;
  overflow: hidden;
}

.timeline-panel.collapsed {
  cursor: pointer;
}

.tl-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  font-weight: 500;
}

.tl-header:hover {
  background: var(--surface2);
}

.tl-toggle {
  font-size: 10px;
  width: 14px;
}

.tl-duration {
  font-size: 12px;
  font-weight: 400;
}

.tl-zoom {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
}

.tl-zoom-slider {
  width: 80px;
  height: 4px;
  accent-color: var(--accent);
}

.tl-zoom-label {
  font-size: 11px;
  min-width: 36px;
  text-align: right;
}

.tl-body {
  border-top: 1px solid var(--border);
  padding: 8px 0;
}

.tl-empty {
  padding: 20px;
  text-align: center;
  font-size: 13px;
}

.tl-scroll {
  overflow-x: auto;
  overflow-y: hidden;
  position: relative;
}

.tl-tracks {
  position: relative;
}

/* Multi-track layout */
.tl-multi-row {
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--border, #333);
  min-height: 36px;
}

.tl-clip-lane {
  flex: 1;
  position: relative;
  min-height: 36px;
  overflow: hidden;
}

.tl-clip-block {
  position: absolute;
  top: 4px;
  height: calc(100% - 8px);
  min-width: 20px;
  background: #3b82f6;
  border-radius: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.65rem;
  color: #fff;
  padding: 0 4px;
  line-height: 28px;
  cursor: pointer;
  user-select: none;
}

.tl-clip-block.selected {
  background: #2563eb;
  outline: 2px solid #93c5fd;
}

.tl-clip-block:hover:not(.selected) {
  background: #2563eb;
}
</style>
