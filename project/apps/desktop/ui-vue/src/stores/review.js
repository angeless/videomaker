/**
 * Review store — manages review sessions, comments, versions, playback, and UI mode.
 * Backs v0.15.0 R11 (ReviewView.vue + all review components).
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'

export const useReviewStore = defineStore('review', () => {
  const apiStore = useApiStore()
  // ── Session state ──
  const sessionId = ref(null)
  const session = ref(null)        // full session object from API
  const status = ref('idle')       // 'idle' | 'loading' | 'ready' | 'error'
  const errorMessage = ref('')

  // ── Comments ──
  const comments = ref([])
  const commentFilter = ref({ type: null, status: null })  // null = all
  const commentSort = ref('time')  // 'time' | 'type' | 'status'

  // ── Versions ──
  const versions = ref([])
  const currentVersion = ref(1)

  // ── Playback ──
  const currentTimeMs = ref(0)
  const durationMs = ref(0)
  const isPlaying = ref(false)
  const playbackRate = ref(1)
  const volume = ref(1)
  const isMuted = ref(false)

  // ── Loop (I/O points) ──
  const loopIn = ref(null)   // ms or null
  const loopOut = ref(null)  // ms or null
  const isLooping = ref(false)

  // ── UI Mode ──
  const mode = ref('normal')  // 'normal' | 'drawing' | 'comment'
  const safeZone = ref(null)  // null | '9:16' | '16:9' | '1:1' | '4:5'

  // ── Zoom / Pan ──
  const zoomLevel = ref(1)
  const panOffset = ref({ x: 0, y: 0 })

  // ── B4b: Stream Analysis ──
  const streamAnalysis = ref(null)   // StreamAnalysis from B4a API
  const sceneSummaries = ref({})     // Dict[scene_idx, SceneSummary]

  // ── Timeline ──
  const timelineScale = ref(1)  // px per second

  // ── Thumbnails + Waveform ──
  const thumbnailData = ref(null)  // { spriteUrl, metadata }
  const waveformData = ref(null)   // { samples[], sampleRate, duration }

  // ── Drawing ──
  const drawingData = ref(null)    // serialized drawing JSON

  // ── Computed ──
  const filteredComments = computed(() => {
    let result = comments.value
    const f = commentFilter.value
    if (f.type) result = result.filter(c => c.comment_type === f.type)
    if (f.status) result = result.filter(c => c.status === f.status)

    const sortKey = commentSort.value
    result = [...result].sort((a, b) => {
      if (sortKey === 'time') return a.time_start_ms - b.time_start_ms
      if (sortKey === 'type') return (a.comment_type || '').localeCompare(b.comment_type || '')
      if (sortKey === 'status') return (a.status || '').localeCompare(b.status || '')
      return 0
    })
    return result
  })

  const pendingComments = computed(() =>
    comments.value.filter(c => c.status === 'pending')
  )

  const currentTimeS = computed(() => currentTimeMs.value / 1000)
  const durationS = computed(() => durationMs.value / 1000)

  const nearbyComments = computed(() => {
    const t = currentTimeMs.value
    const threshold = 2000  // 2s window
    return filteredComments.value.filter(c =>
      c.time_start_ms >= t - threshold && c.time_start_ms <= t + threshold
    )
  })

  // ── API helpers ──
  // Signature deliberately matches apiStore.api(method, url, body) so callers
  // can use the same idiom across stores. Routes through apiStore so auth
  // (X-VideoEditor-Token + CSRF) and friendlyErrorMessage processing happen
  // automatically. Bare `fetch()` here previously broke under the local-token
  // auth gate AND made ExportDialog/EnhancePanel completely non-functional
  // because they were calling `_fetch('GET', url)` with the old (url, options)
  // signature — the method string was being treated as the URL.
  async function _fetch(method, url, body) {
    const data = await apiStore.api(method, url, body)
    if (!data || data.error) {
      const msg = (data && data.error) || 'API error'
      errorMessage.value = msg
      throw new Error(msg)
    }
    if (data.success === false) {
      const msg = data.message || 'API error'
      errorMessage.value = msg
      throw new Error(msg)
    }
    return data
  }

  // ── Session actions ──
  async function initSession(projectPath, videoPath, videoType, speechRatio = 0) {
    status.value = 'loading'
    errorMessage.value = ''
    try {
      const data = await _fetch('POST', '/api/review/init', {
        project_path: projectPath,
        video_path: videoPath,
        video_type: videoType,
        speech_ratio: speechRatio,
      })
      sessionId.value = data.session_id
      await loadState()
      status.value = 'ready'
      return data
    } catch (e) {
      status.value = 'error'
      throw e
    }
  }

  async function loadFromSession(existingSessionId) {
    sessionId.value = existingSessionId
    status.value = 'loading'
    errorMessage.value = ''
    try {
      await Promise.all([loadState(), loadComments(), loadVersions()])
      status.value = 'ready'
    } catch (e) {
      status.value = 'error'
      throw e
    }
  }

  async function loadState() {
    if (!sessionId.value) return
    const data = await _fetch('GET', `/api/review/${sessionId.value}/state`)
    session.value = data.session
    currentVersion.value = data.session.current_version
  }

  // ── Comment actions ──
  async function loadComments(version = null) {
    if (!sessionId.value) return
    const url = version != null
      ? `/api/review/${sessionId.value}/comments?version=${version}`
      : `/api/review/${sessionId.value}/comments`
    const data = await _fetch('GET', url)
    comments.value = data.comments || []
  }

  async function addComment({ timeStartMs, timeEndMs, commentType, text, drawingData: drawing, visualContext: vc }) {
    if (!sessionId.value) return
    const data = await _fetch('POST', `/api/review/${sessionId.value}/comments`, {
      version: currentVersion.value,
      time_start_ms: timeStartMs,
      time_end_ms: timeEndMs || null,
      comment_type: commentType,
      text,
      drawing_data: drawing || null,
      visual_context: vc || null,
    })
    await loadComments()
    return data
  }

  async function updateComment(commentId, fields) {
    const data = await _fetch('PATCH', `/api/review/comments/${commentId}`, fields)
    await loadComments()
    return data
  }

  async function deleteComment(commentId) {
    const data = await _fetch('DELETE', `/api/review/comments/${commentId}`)
    await loadComments()
    return data
  }

  async function resolveComment(commentId) {
    return updateComment(commentId, {
      status: 'resolved',
      resolved_in_version: currentVersion.value,
    })
  }

  // ── Version actions ──
  async function loadVersions() {
    if (!sessionId.value) return
    const data = await _fetch('GET', `/api/review/${sessionId.value}/versions`)
    versions.value = data.versions || []
  }

  async function switchVersion(versionNumber) {
    currentVersion.value = versionNumber
    await loadComments(versionNumber)
  }

  async function rollbackTo(versionNumber) {
    if (!sessionId.value) return
    const data = await _fetch('POST', `/api/review/${sessionId.value}/rollback/${versionNumber}`)
    currentVersion.value = data.new_version
    await Promise.all([loadVersions(), loadComments()])
    return data
  }

  // ── Playback actions ──
  function seekTo(ms) {
    currentTimeMs.value = Math.max(0, Math.min(ms, durationMs.value))
  }

  function seekByFrames(frames, fps = 30) {
    const deltaMs = (frames / fps) * 1000
    seekTo(currentTimeMs.value + deltaMs)
  }

  function setLoopIn() {
    loopIn.value = currentTimeMs.value
  }

  function setLoopOut() {
    loopOut.value = currentTimeMs.value
  }

  function toggleLoop() {
    if (loopIn.value != null && loopOut.value != null) {
      isLooping.value = !isLooping.value
    }
  }

  function clearLoop() {
    loopIn.value = null
    loopOut.value = null
    isLooping.value = false
  }

  // ── UI mode ──
  function enterDrawingMode() { mode.value = 'drawing' }
  function enterCommentMode() { mode.value = 'comment' }
  function exitMode() { mode.value = 'normal' }

  function cycleSafeZone() {
    const zones = [null, '9:16', '16:9', '1:1', '4:5']
    const idx = zones.indexOf(safeZone.value)
    safeZone.value = zones[(idx + 1) % zones.length]
  }

  // ── Zoom ──
  function setZoom(level) {
    zoomLevel.value = Math.max(1, Math.min(4, level))
    if (zoomLevel.value === 1) panOffset.value = { x: 0, y: 0 }
  }

  function resetZoom() {
    zoomLevel.value = 1
    panOffset.value = { x: 0, y: 0 }
  }

  // ── Reset ──
  function reset() {
    sessionId.value = null
    session.value = null
    status.value = 'idle'
    errorMessage.value = ''
    comments.value = []
    commentFilter.value = { type: null, status: null }
    commentSort.value = 'time'
    versions.value = []
    currentVersion.value = 1
    currentTimeMs.value = 0
    durationMs.value = 0
    isPlaying.value = false
    playbackRate.value = 1
    volume.value = 1
    isMuted.value = false
    loopIn.value = null
    loopOut.value = null
    isLooping.value = false
    mode.value = 'normal'
    safeZone.value = null
    zoomLevel.value = 1
    panOffset.value = { x: 0, y: 0 }
    timelineScale.value = 1
    thumbnailData.value = null
    waveformData.value = null
    drawingData.value = null
  }

  return {
    // State
    sessionId, session, status, errorMessage,
    comments, commentFilter, commentSort,
    versions, currentVersion,
    currentTimeMs, durationMs, isPlaying, playbackRate, volume, isMuted,
    loopIn, loopOut, isLooping,
    mode, safeZone, zoomLevel, panOffset,
    timelineScale, thumbnailData, waveformData, drawingData,
    streamAnalysis, sceneSummaries,
    // Computed
    filteredComments, pendingComments, currentTimeS, durationS, nearbyComments,
    // Session
    initSession, loadFromSession, loadState,
    // Comments
    loadComments, addComment, updateComment, deleteComment, resolveComment,
    // Generic API helper exposed for components (ExportDialog, EnhancePanel)
    _fetch,
    // Versions
    loadVersions, switchVersion, rollbackTo,
    // Playback
    seekTo, seekByFrames, setLoopIn, setLoopOut, toggleLoop, clearLoop,
    // UI
    enterDrawingMode, enterCommentMode, exitMode, cycleSafeZone,
    setZoom, resetZoom,
    // Reset
    reset,
  }
})
