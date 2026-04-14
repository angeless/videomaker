<template>
  <div class="titlebar">
    <span class="title">评审模式</span>
    <span class="title-sep">—</span>
    <span class="title-detail" v-if="store.session">{{ sessionName }}</span>
    <div class="titlebar-spacer"></div>
    <VersionSwitcher v-if="store.status === 'ready'" />
    <router-link to="/roughcut" class="btn btn-ghost btn-sm">← 返回粗剪</router-link>
  </div>

  <div class="review-layout" v-if="store.status === 'ready'">
    <!-- Main area: player + sidebar -->
    <div class="rl-main">
      <!-- Player area -->
      <div class="rl-player-area">
        <ReviewPlayer ref="playerRef">
          <template #overlay>
            <SafeZoneOverlay v-if="store.safeZone" :ratio="store.safeZone" />
            <DrawingOverlay ref="drawingRef" @annotationComplete="onAnnotationComplete" />
            <AnnotationToolbar
              @undo="drawingRef?.undo()"
              @redo="drawingRef?.redo()"
              @clear="drawingRef?.clear()"
              @toolChange="t => { if (drawingRef) drawingRef.tool = t }"
              @colorChange="c => { if (drawingRef) drawingRef.color = c }"
              @widthChange="w => { if (drawingRef) drawingRef.lineWidth = w }"
            />
          </template>
        </ReviewPlayer>
        <PlayerControls
          :fps="playerRef?.fps || 30"
          @togglePlay="playerRef?.togglePlay()"
          @prevFrame="playerRef?.seekByFrames(-1)"
          @nextFrame="playerRef?.seekByFrames(1)"
          @back5s="playerRef?.seek(store.currentTimeMs - 5000)"
          @forward5s="playerRef?.seek(store.currentTimeMs + 5000)"
          @seek="ms => playerRef?.seek(ms)"
          @setLoopIn="store.setLoopIn()"
          @setLoopOut="store.setLoopOut()"
          @toggleLoop="store.toggleLoop()"
          @toggleFullscreen="playerRef?.toggleFullscreen()"
          @zoomReset="store.resetZoom()"
        />
        <!-- Floating comment input -->
        <CommentInput
          ref="commentInputRef"
          @submitted="onCommentSubmitted"
          @cancelled="onCommentCancelled"
        />
      </div>

      <!-- Sidebar: comments + diagnostics + render -->
      <div class="rl-sidebar">
        <CommentPanel @seek="ms => playerRef?.seek(ms)" />
        <DiagnosticsPanel />
        <RenderProgress ref="renderProgressRef" />
        <button class="btn btn-primary btn-sm" style="margin: 8px" @click="startRender">渲染</button>
      </div>
    </div>

    <!-- Timeline area -->
    <ReviewTimeline ref="timelineRef" @seek="ms => playerRef?.seek(ms)">
      <template #comments>
        <TrackComments
          :pxPerSec="timelineRef?.pxPerSec || 80"
          @seek="ms => playerRef?.seek(ms)"
        />
      </template>
      <template #thumbnails>
        <ThumbnailStrip :pxPerSec="timelineRef?.pxPerSec || 80" />
      </template>
      <template #waveform>
        <WaveformTrack :pxPerSec="timelineRef?.pxPerSec || 80" />
      </template>
      <template #subtitles>
        <!-- SubtitleEditor requires subtitle data — connected when available -->
      </template>
    </ReviewTimeline>
  </div>

  <!-- Loading state -->
  <div v-else-if="store.status === 'loading'" class="review-loading">
    <div class="spinner"></div>
    <p>加载评审会话中…</p>
  </div>

  <!-- Error state -->
  <div v-else-if="store.status === 'error'" class="review-error">
    <p class="error-text">{{ store.errorMessage || '加载失败' }}</p>
    <button class="btn btn-primary btn-sm" @click="retry">重试</button>
    <router-link to="/roughcut" class="btn btn-ghost btn-sm">返回粗剪</router-link>
  </div>

  <!-- Idle: no session -->
  <div v-else class="review-idle">
    <p>未找到评审会话。请从粗剪页面进入评审。</p>
    <router-link to="/roughcut" class="btn btn-primary btn-sm">前往粗剪</router-link>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useReviewStore } from '../stores/review.js'
import { useApiStore } from '../stores/api.js'
import { useKeyboardShortcuts } from '../composables/useKeyboardShortcuts.js'
import ReviewPlayer from '../components/review/ReviewPlayer.vue'
import PlayerControls from '../components/review/PlayerControls.vue'
import ReviewTimeline from '../components/review/ReviewTimeline.vue'
import CommentPanel from '../components/review/CommentPanel.vue'
import CommentInput from '../components/review/CommentInput.vue'
import TrackComments from '../components/review/TrackComments.vue'
import DrawingOverlay from '../components/review/DrawingOverlay.vue'
import AnnotationToolbar from '../components/review/AnnotationToolbar.vue'
import SafeZoneOverlay from '../components/review/SafeZoneOverlay.vue'
import ThumbnailStrip from '../components/review/ThumbnailStrip.vue'
import WaveformTrack from '../components/review/WaveformTrack.vue'
import VersionSwitcher from '../components/review/VersionSwitcher.vue'
import DiagnosticsPanel from '../components/review/DiagnosticsPanel.vue'
import RenderProgress from '../components/review/RenderProgress.vue'

const store = useReviewStore()
const apiStore = useApiStore()
const route = useRoute()
const playerRef = ref(null)
const timelineRef = ref(null)
const commentInputRef = ref(null)
const drawingRef = ref(null)
const renderProgressRef = ref(null)

function startRender() {
  if (store.sessionId) {
    renderProgressRef.value?.startRender(store.sessionId)
  }
}

const sessionName = computed(() => {
  if (!store.session?.video_path) return ''
  const parts = store.session.video_path.split('/')
  return parts[parts.length - 1]
})

// ── Initialize session from route query ──
onMounted(async () => {
  const sid = route.query.session_id
  if (sid) {
    await store.loadFromSession(sid)
  }
})

onUnmounted(() => {
  store.reset()
})

// ── Speed helpers ──
const SPEEDS = [0.25, 0.5, 1, 1.5, 2, 4]

function speedDown() {
  const idx = SPEEDS.indexOf(store.playbackRate)
  if (idx > 0) store.playbackRate = SPEEDS[idx - 1]
}

function speedUp() {
  const idx = SPEEDS.indexOf(store.playbackRate)
  if (idx < SPEEDS.length - 1) store.playbackRate = SPEEDS[idx + 1]
}

// ── Keyboard shortcuts ──
useKeyboardShortcuts(computed(() => store.mode), {
  // Playback
  play_pause: () => playerRef.value?.togglePlay(),
  prev_frame: () => playerRef.value?.seekByFrames(-1),
  next_frame: () => playerRef.value?.seekByFrames(1),
  back_5s: () => playerRef.value?.seek(store.currentTimeMs - 5000),
  forward_5s: () => playerRef.value?.seek(store.currentTimeMs + 5000),
  speed_down: speedDown,
  speed_up: speedUp,

  // I/O Loop
  set_loop_in: () => store.setLoopIn(),
  set_loop_out: () => store.setLoopOut(),
  toggle_loop: () => store.toggleLoop(),

  // Comments
  open_comment: () => store.enterCommentMode(),
  prev_comment: () => navigateComment(-1),
  next_comment: () => navigateComment(1),
  comment_type_1: () => commentInputRef.value?.selectTypeByKey('1'),
  comment_type_2: () => commentInputRef.value?.selectTypeByKey('2'),
  comment_type_3: () => commentInputRef.value?.selectTypeByKey('3'),
  comment_type_4: () => commentInputRef.value?.selectTypeByKey('4'),
  comment_type_5: () => commentInputRef.value?.selectTypeByKey('5'),
  comment_type_6: () => commentInputRef.value?.selectTypeByKey('6'),
  comment_type_7: () => commentInputRef.value?.selectTypeByKey('7'),
  submit_comment: () => commentInputRef.value?.submit?.(),

  // Drawing
  enter_drawing: () => store.enterDrawingMode(),
  undo: () => drawingRef.value?.undo(),
  redo: () => drawingRef.value?.redo(),

  // View
  toggle_fullscreen: () => playerRef.value?.toggleFullscreen(),
  cycle_safe_zone: () => store.cycleSafeZone(),
  zoom_in: () => store.setZoom(store.zoomLevel + 0.25),
  zoom_out: () => store.setZoom(store.zoomLevel - 0.25),
  zoom_reset: () => store.resetZoom(),

  // Versions
  prev_version: () => switchVersionDelta(-1),
  next_version: () => switchVersionDelta(1),

  // Timeline zoom
  timeline_zoom_in: () => timelineRef.value?.zoomIn(),
  timeline_zoom_out: () => timelineRef.value?.zoomOut(),

  // Escape
  escape: () => {
    if (store.mode !== 'normal') store.exitMode()
  },
})

// ── Comment navigation ──
function navigateComment(delta) {
  const comments = store.filteredComments
  if (!comments.length) return
  const t = store.currentTimeMs
  let idx = comments.findIndex(c => c.time_start_ms > t)
  if (delta < 0) {
    idx = comments.findLastIndex(c => c.time_start_ms < t)
    if (idx < 0) idx = comments.length - 1
  } else {
    if (idx < 0) idx = 0
  }
  if (comments[idx]) {
    playerRef.value?.seek(comments[idx].time_start_ms)
  }
}

// ── Version navigation ──
function switchVersionDelta(delta) {
  const next = store.currentVersion + delta
  if (next >= 1 && next <= store.versions.length) {
    store.switchVersion(next)
  }
}

function onCommentSubmitted() {
  // Comment added — panel auto-refreshes via store
}

function onCommentCancelled() {
  // Back to normal mode
}

// ── R8/R7 (v0.17.0): VLM annotation handler ──
async function onAnnotationComplete({ strokes, frameDataUrl, timestamp_ms }) {
  if (!store.sessionId || !frameDataUrl) return
  commentInputRef.value?.setAiHintLoading(true)
  try {
    const frameB64 = frameDataUrl.split(',')[1]
    // Route through apiStore so X-VideoEditor-Token + CSRF are attached;
    // raw fetch was 401-ing in token-required mode and the silent catch
    // hid the failure from users.
    const data = await apiStore.api(
      'POST',
      `/api/review/${store.sessionId}/vlm/describe`,
      { frame_base64: frameB64, strokes, timestamp_ms },
    )
    if (data && !data.error && data.success && data.description) {
      commentInputRef.value?.setAiHint(data.description)
    }
  } finally {
    commentInputRef.value?.setAiHintLoading(false)
  }
}

function retry() {
  const sid = route.query.session_id
  if (sid) store.loadFromSession(sid)
}
</script>

<style scoped>
.titlebar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  background: #111;
  border-bottom: 1px solid #333;
  gap: 8px;
  -webkit-app-region: drag;
}

.title {
  font-weight: 600;
  font-size: 0.85rem;
  color: #eee;
}

.title-sep {
  color: #444;
}

.title-detail {
  font-size: 0.75rem;
  color: #888;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.titlebar-spacer {
  flex: 1;
}

/* Layout */
.review-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 40px);
  overflow: hidden;
}

.rl-main {
  display: flex;
  flex: 1;
  min-height: 0;
}

.rl-player-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
}

.rl-sidebar {
  width: 300px;
  min-width: 240px;
  max-width: 400px;
  flex-shrink: 0;
}

/* Loading / Error / Idle states */
.review-loading,
.review-error,
.review-idle {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 40px);
  gap: 12px;
  color: #888;
  font-size: 0.9rem;
}

.error-text {
  color: #ef4444;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #333;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Shared button styles (matching existing app conventions) */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  text-decoration: none;
  -webkit-app-region: no-drag;
}

.btn-primary {
  background: #3b82f6;
  color: #fff;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-ghost {
  background: transparent;
  color: #888;
}

.btn-ghost:hover {
  color: #fff;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 0.75rem;
}
</style>
