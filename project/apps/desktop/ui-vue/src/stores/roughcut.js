/**
 * Roughcut store — manages smart rough cut sessions, transcripts, scenes, and edits.
 * Backs R9-R13 (TranscriptEditor), R16 (SceneSelector), R19 (RoughCutView).
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'

export const useRoughcutStore = defineStore('roughcut', () => {
  const apiStore = useApiStore()
  // ── Session state ──
  const sessionId = ref(null)
  const videoPath = ref('')
  const videoType = ref('')     // 'speech' | 'scenic' | 'mixed'
  const speechRatio = ref(0)
  const status = ref('idle')    // 'idle' | 'loading' | 'ready' | 'rendering' | 'error'
  const errorMessage = ref('')

  // ── Transcript (R9-R13) ──
  const transcript = ref(null)  // { video_path, duration_ms, language, paragraphs[] }
  const fillers = ref([])       // filler marks from API

  // ── Scenes (R16) ──
  const scenes = ref([])        // SceneInfo[] from API

  // ── Playback ──
  const currentTimeMs = ref(0)
  const isPlaying = ref(false)

  // ── Version ──
  const currentVersion = ref(1)
  const stats = ref({ totalComments: 0, totalVersions: 0 })

  // ── Computed ──
  const paragraphs = computed(() => transcript.value?.paragraphs || [])
  const activeParagraphs = computed(() => paragraphs.value.filter(p => !p.is_deleted))
  const estimatedDurationMs = computed(() =>
    activeParagraphs.value.reduce((sum, p) => sum + (p.end_ms - p.start_ms), 0)
  )
  const selectedScenes = computed(() => scenes.value.filter(s => s.selected))

  // ── API helpers ──
  // Routes through apiStore to attach X-VideoEditor-Token + CSRF (raw fetch
  // would 401/403 in token-required mode). Signature mirrors apiStore.api.
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

  // ── Actions ──
  async function initSession(projectPath, videoFilePath) {
    status.value = 'loading'
    errorMessage.value = ''
    try {
      const data = await _fetch('POST', '/api/roughcut/init', {
        project_path: projectPath,
        video_path: videoFilePath,
      })
      sessionId.value = data.session_id
      videoPath.value = videoFilePath
      videoType.value = data.video_type
      speechRatio.value = data.speech_ratio
      status.value = 'ready'
      return data
    } catch (e) {
      status.value = 'error'
      throw e
    }
  }

  async function loadTranscript() {
    if (!sessionId.value) return
    status.value = 'loading'
    try {
      const data = await _fetch('GET', `/api/roughcut/${sessionId.value}/transcript`)
      transcript.value = data.transcript
      status.value = 'ready'
    } catch (e) {
      status.value = 'error'
    }
  }

  async function loadFillers() {
    if (!sessionId.value) return
    const data = await _fetch('GET', `/api/roughcut/${sessionId.value}/fillers`)
    fillers.value = data.fillers || []
  }

  async function loadScenes() {
    if (!sessionId.value) return
    status.value = 'loading'
    try {
      const data = await _fetch('GET', `/api/roughcut/${sessionId.value}/scenes`)
      scenes.value = (data.scenes || []).map(s => ({ ...s, selected: s.selected ?? true }))
      status.value = 'ready'
    } catch (e) {
      status.value = 'error'
    }
  }

  async function loadStats() {
    if (!sessionId.value) return
    const data = await _fetch('GET', `/api/roughcut/${sessionId.value}/stats`)
    stats.value = {
      totalComments: data.total_comments,
      totalVersions: data.total_versions,
    }
    currentVersion.value = data.current_version
  }

  // ── Paragraph editing (R12) ──
  function deleteParagraph(idx) {
    if (!transcript.value) return
    const p = transcript.value.paragraphs.find(p => p.idx === idx)
    if (p) p.is_deleted = true
  }

  function restoreParagraph(idx) {
    if (!transcript.value) return
    const p = transcript.value.paragraphs.find(p => p.idx === idx)
    if (p) p.is_deleted = false
  }

  function toggleParagraph(idx) {
    if (!transcript.value) return
    const p = transcript.value.paragraphs.find(p => p.idx === idx)
    if (p) p.is_deleted = !p.is_deleted
  }

  async function submitEdits(operations) {
    if (!sessionId.value) return
    const data = await _fetch('POST', `/api/roughcut/${sessionId.value}/transcript/edit`, {
      operations,
    })
    currentVersion.value = data.version
    return data
  }

  async function batchRemoveFillers(fillerTypes = []) {
    if (!sessionId.value) return
    const data = await _fetch('POST', `/api/roughcut/${sessionId.value}/fillers/batch`, {
      action: 'remove',
      filler_types: fillerTypes,
    })
    return data
  }

  // ── Scene selection (R16) ──
  function toggleScene(sceneIdx) {
    const s = scenes.value.find(s => s.scene_idx === sceneIdx)
    if (s) s.selected = !s.selected
  }

  function selectAllScenes() {
    scenes.value.forEach(s => { s.selected = true })
  }

  function deselectAllScenes() {
    scenes.value.forEach(s => { s.selected = false })
  }

  async function submitSceneSelection() {
    if (!sessionId.value) return
    const selected = scenes.value.filter(s => s.selected).map(s => s.scene_idx)
    const data = await _fetch('POST', `/api/roughcut/${sessionId.value}/scenes/select`, {
      selected,
    })
    currentVersion.value = data.version
    return data
  }

  // ── Generate rough cut (R22) ──
  async function generateRoughCut() {
    if (!sessionId.value) return
    status.value = 'rendering'
    try {
      const data = await _fetch('POST', `/api/roughcut/${sessionId.value}/generate`, {})
      status.value = 'ready'
      return data
    } catch (e) {
      status.value = 'error'
      throw e
    }
  }

  // ── Playback (R11) ──
  function seekTo(ms) {
    currentTimeMs.value = ms
  }

  // ── Reset ──
  function reset() {
    sessionId.value = null
    videoPath.value = ''
    videoType.value = ''
    speechRatio.value = 0
    status.value = 'idle'
    errorMessage.value = ''
    transcript.value = null
    fillers.value = []
    scenes.value = []
    currentTimeMs.value = 0
    isPlaying.value = false
    currentVersion.value = 1
    stats.value = { totalComments: 0, totalVersions: 0 }
  }

  return {
    // State
    sessionId, videoPath, videoType, speechRatio,
    status, errorMessage,
    transcript, fillers, scenes,
    currentTimeMs, isPlaying,
    currentVersion, stats,
    // Computed
    paragraphs, activeParagraphs, estimatedDurationMs, selectedScenes,
    // Actions
    initSession, loadTranscript, loadFillers, loadScenes, loadStats,
    deleteParagraph, restoreParagraph, toggleParagraph,
    submitEdits, batchRemoveFillers,
    toggleScene, selectAllScenes, deselectAllScenes, submitSceneSelection,
    generateRoughCut, seekTo, reset,
  }
})
