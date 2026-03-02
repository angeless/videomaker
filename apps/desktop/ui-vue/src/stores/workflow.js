import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'
import { useAppStore } from './app.js'
import { useToastStore } from './toast.js'
import labels from '../i18n/labels.js'

export const useWorkflowStore = defineStore('workflow', () => {
  const api = useApiStore()
  const toast = useToastStore()

  // ── 步骤状态 ──
  const activeStep = ref(1)
  const stepData = ref({})

  // ── Job 状态 ──
  const jobId = ref('')
  const jobStatus = ref('')
  const jobLog = ref([])
  const jobRunning = ref(false)
  const jobProgress = ref(0)

  // ── Step 1: 素材选择 ──
  const selectedAssets = ref([])
  const maxSelectedAssets = ref(50)

  // ── Step 2: 选题 ──
  const topics = ref([])
  const selectedTopic = ref(null)
  const topicCustom = ref('')

  // ── Step 3: 脚本 ──
  const scriptClips = ref([])
  const scriptSubs = ref([])
  const scriptJson = ref('')
  const scriptView = ref('visual')

  // ── Step 4: 素材匹配（自动）──

  // ── Step 5: 帧预览 ──
  const frames = ref([])

  // ── Step 6: 粗剪 ──
  const roughUrl = ref('')
  const renderOpts = ref({
    width: 1080, height: 1920, fps: 30, crf: 18, preset: 'medium',
    enable_skin_smooth: true, enable_color_grading: true,
    enable_skill_enhance: true,
    aesthetic_preset: 'travel_story',
    transition_style: 'fade',
    transition_duration: 0.35,
    rough_target_seconds: 15,
    rough_max_clips: 8,
    rough_merge_gap_s: 0.15,
    rough_remove_phrases: '嗯,啊,然后,就是,那个',
    skin_smooth_strength: 0.4,
    bgm_path: '', bgm_volume: 0.35, narration_path: '',
    subtitle_font: 'PingFangSC-Regular', subtitle_size: 56,
  })

  // ── Step 7: 精渲染 ──
  const stageFiles = ref({})
  const finalUrl = ref('')
  const stageNames = ref([
    '片段剪切 & 合并',
    '美颜滤镜',
    '色彩调级',
    '字幕压制',
    'BGM 混音',
  ])

  // ── 计算属性 ──
  const stepLabels = computed(() => labels.workflow.steps)

  // ── Step 数据操作 ──

  async function loadStepData() {
    const appStore = useAppStore()
    if (!appStore.projectDir) return
    const data = await api.api('GET', '/api/workflow/status')
    if (data.error) return
    appStore.currentStep = data.current_step || 1
    appStore.steps = data.steps || []

    if (data.materials) {
      // 解析素材数据
    }
    if (data.topics) topics.value = data.topics
    if (data.script_clips) scriptClips.value = data.script_clips
    if (data.script_subs) scriptSubs.value = data.script_subs
    if (data.frames) frames.value = data.frames
    if (data.rough_url) roughUrl.value = data.rough_url
    if (data.stage_files) stageFiles.value = data.stage_files
    if (data.final_url) finalUrl.value = data.final_url
  }

  async function runStep(step) {
    jobRunning.value = true
    jobStatus.value = ''
    jobLog.value = []
    jobProgress.value = 0

    const data = await api.api('POST', `/api/workflow/step/${step}/run`)
    if (data.error) {
      jobRunning.value = false
      toast.show(data.error, 'danger')
      return
    }

    jobId.value = data.job_id || ''
    if (jobId.value) {
      pollJob()
    }
  }

  async function approveStep(step) {
    const data = await api.api('POST', `/api/workflow/step/${step}/approve`)
    if (data.error) {
      toast.show(data.error, 'danger')
      return
    }
    toast.show('已确认通过', 'success')
    await loadStepData()
  }

  // ── Job 轮询 ──

  let _pollTimer = null
  let _lastJobJson = ''

  async function pollJob() {
    if (!jobId.value) return
    const data = await api.api('GET', `/api/job/${jobId.value}`)
    if (data.error) {
      jobRunning.value = false
      toast.show(data.error, 'danger')
      return
    }

    const incoming = JSON.stringify(data)
    if (incoming !== _lastJobJson) {
      _lastJobJson = incoming
      jobStatus.value = data.status || ''
      jobProgress.value = data.progress || 0
      if (Array.isArray(data.log)) {
        jobLog.value = data.log
      }
    }

    const status = `${data.status || ''}`.toLowerCase()
    if (status === 'completed' || status === 'done') {
      jobRunning.value = false
      toast.show('执行完成', 'success')
      await loadStepData()
      return
    }
    if (status === 'error' || status === 'failed') {
      jobRunning.value = false
      toast.show(data.error || '执行失败', 'danger')
      return
    }

    _pollTimer = setTimeout(() => pollJob(), 1500)
  }

  function cancelPoll() {
    if (_pollTimer) {
      clearTimeout(_pollTimer)
      _pollTimer = null
    }
  }

  return {
    activeStep,
    stepData,
    jobId,
    jobStatus,
    jobLog,
    jobRunning,
    jobProgress,
    selectedAssets,
    maxSelectedAssets,
    topics,
    selectedTopic,
    topicCustom,
    scriptClips,
    scriptSubs,
    scriptJson,
    scriptView,
    frames,
    roughUrl,
    renderOpts,
    stageFiles,
    finalUrl,
    stageNames,
    stepLabels,
    loadStepData,
    runStep,
    approveStep,
    pollJob,
    cancelPoll,
  }
})
