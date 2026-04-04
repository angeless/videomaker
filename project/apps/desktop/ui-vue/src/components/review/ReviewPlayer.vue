<template>
  <div
    class="review-player"
    :class="{ 'is-fullscreen': isFullscreen }"
    ref="containerRef"
    @wheel.meta.prevent="onWheelZoom"
  >
    <!-- Video element -->
    <div
      class="player-viewport"
      :style="viewportStyle"
      @mousedown="onPanStart"
      @mousemove="onPanMove"
      @mouseup="onPanEnd"
    >
      <video
        ref="videoRef"
        :src="videoSrc"
        @loadedmetadata="onLoadedMetadata"
        @timeupdate="onTimeUpdate"
        @ended="onEnded"
        @error="onError"
        @play="store.isPlaying = true"
        @pause="store.isPlaying = false"
        preload="auto"
        crossorigin="anonymous"
      ></video>

      <!-- Overlay slot (drawing, safe zone, etc.) -->
      <div class="player-overlay">
        <slot name="overlay"></slot>
      </div>

      <!-- Error overlay -->
      <div v-if="loadError" class="player-error">
        <span class="player-error-icon">&#9888;</span>
        <p>{{ loadError }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()

const videoRef = ref(null)
const containerRef = ref(null)
const loadError = ref('')
const isFullscreen = ref(false)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const fps = ref(30)

// Video source — serve from local file system via pywebview
const videoSrc = computed(() => {
  if (!store.session?.video_path) return ''
  return `/api/file?path=${encodeURIComponent(store.session.video_path)}`
})

const viewportStyle = computed(() => {
  const z = store.zoomLevel
  const p = store.panOffset
  return {
    transform: `scale(${z}) translate(${p.x}px, ${p.y}px)`,
    transformOrigin: 'center center',
    cursor: z > 1 ? (isPanning.value ? 'grabbing' : 'grab') : 'default',
  }
})

// ── Video event handlers ──
function onLoadedMetadata() {
  const video = videoRef.value
  if (!video) return
  store.durationMs = Math.round(video.duration * 1000)
  loadError.value = ''
  // Detect fps from video metadata (fallback to 30)
  // Note: HTML5 video doesn't expose fps directly
}

function onTimeUpdate() {
  const video = videoRef.value
  if (!video) return
  const ms = Math.round(video.currentTime * 1000)
  store.currentTimeMs = ms

  // Loop enforcement
  if (store.isLooping && store.loopOut != null) {
    if (ms >= store.loopOut) {
      video.currentTime = (store.loopIn || 0) / 1000
    }
  }
}

function onEnded() {
  store.isPlaying = false
  if (store.isLooping && store.loopIn != null) {
    const video = videoRef.value
    if (video) {
      video.currentTime = store.loopIn / 1000
      video.play()
    }
  }
}

function onError() {
  loadError.value = '视频加载失败，请检查文件路径'
  store.isPlaying = false
}

// ── Playback control (called from store watchers or keyboard shortcuts) ──
function play() {
  videoRef.value?.play()
}

function pause() {
  videoRef.value?.pause()
}

function togglePlay() {
  if (store.isPlaying) pause()
  else play()
}

function seek(ms) {
  const video = videoRef.value
  if (!video) return
  const clamped = Math.max(0, Math.min(ms, store.durationMs))
  video.currentTime = clamped / 1000
  store.currentTimeMs = clamped
}

function seekByFrames(frames) {
  const deltaMs = (frames / fps.value) * 1000
  seek(store.currentTimeMs + deltaMs)
}

// ── Zoom / Pan ──
function onWheelZoom(e) {
  const delta = e.deltaY > 0 ? -0.25 : 0.25
  store.setZoom(store.zoomLevel + delta)
}

function onPanStart(e) {
  if (store.zoomLevel <= 1) return
  isPanning.value = true
  panStart.value = { x: e.clientX - store.panOffset.x, y: e.clientY - store.panOffset.y }
}

function onPanMove(e) {
  if (!isPanning.value) return
  store.panOffset = {
    x: e.clientX - panStart.value.x,
    y: e.clientY - panStart.value.y,
  }
}

function onPanEnd() {
  isPanning.value = false
}

// ── Fullscreen ──
function toggleFullscreen() {
  const el = containerRef.value
  if (!el) return
  if (!document.fullscreenElement) {
    el.requestFullscreen?.()
    isFullscreen.value = true
  } else {
    document.exitFullscreen?.()
    isFullscreen.value = false
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

// ── Watch store changes ──
watch(() => store.playbackRate, (rate) => {
  if (videoRef.value) videoRef.value.playbackRate = rate
})

watch(() => store.volume, (vol) => {
  if (videoRef.value) videoRef.value.volume = vol
})

watch(() => store.isMuted, (muted) => {
  if (videoRef.value) videoRef.value.muted = muted
})

// ── Lifecycle ──
onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})

// Expose methods for parent / keyboard handler
defineExpose({
  play, pause, togglePlay, seek, seekByFrames, toggleFullscreen, fps,
})
</script>

<style scoped>
.review-player {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
  border-radius: 4px;
}

.review-player.is-fullscreen {
  border-radius: 0;
}

.player-viewport {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.1s ease-out;
}

.player-viewport video {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.player-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.player-overlay > * {
  pointer-events: auto;
}

.player-error {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.8);
  color: #ef4444;
}

.player-error-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.player-error p {
  font-size: 0.875rem;
  color: #fca5a5;
}
</style>
