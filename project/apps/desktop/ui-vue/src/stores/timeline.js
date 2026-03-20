import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'

export const useTimelineStore = defineStore('timeline', () => {
  const api = useApiStore()

  const timelineData = ref(null)
  const zoom = ref(1.0)
  const playheadTime = ref(0)
  const selectedClipIndex = ref(null)
  const visible = ref(false)
  const loading = ref(false)

  const clips = computed(() => timelineData.value?.clips || [])
  const subtitles = computed(() => timelineData.value?.subtitles || [])
  const totalDuration = computed(() => timelineData.value?.total_duration || 0)
  const audio = computed(() => timelineData.value?.audio || {})
  const transition = computed(() => timelineData.value?.transition || { style: 'fade', duration: 0.35 })

  const selectedClip = computed(() => {
    if (selectedClipIndex.value == null) return null
    return clips.value.find(c => c.clip_index === selectedClipIndex.value) || null
  })

  async function loadTimeline() {
    loading.value = true
    const data = await api.api('GET', '/api/timeline')
    loading.value = false
    if (data.error) return
    timelineData.value = data.timeline || null
  }

  function selectClip(idx) {
    selectedClipIndex.value = selectedClipIndex.value === idx ? null : idx
  }

  function setPlayhead(t) {
    playheadTime.value = Math.max(0, Math.min(t, totalDuration.value))
  }

  function setZoom(z) {
    zoom.value = Math.max(0.25, Math.min(4.0, z))
  }

  function toggleVisible() {
    visible.value = !visible.value
    if (visible.value && !timelineData.value) {
      loadTimeline()
    }
  }

  return {
    timelineData,
    zoom,
    playheadTime,
    selectedClipIndex,
    visible,
    loading,
    clips,
    subtitles,
    totalDuration,
    audio,
    transition,
    selectedClip,
    loadTimeline,
    selectClip,
    setPlayhead,
    setZoom,
    toggleVisible,
  }
})
