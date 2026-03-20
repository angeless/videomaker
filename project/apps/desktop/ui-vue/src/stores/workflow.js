import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'
import { useAppStore } from './app.js'
import { useToastStore } from './toast.js'
import { useNotificationsStore } from './notifications.js'
import labels from '../i18n/labels.js'

export const useWorkflowStore = defineStore('workflow', () => {
  const api = useApiStore()
  const toast = useToastStore()
  const notifications = useNotificationsStore()

  // ── rate-limit 检测 ──
  function _isRateLimitError(msg) {
    const s = `${msg || ''}`.toLowerCase()
    return s.includes('429') || s.includes('rate limit') || s.includes('rate_limit')
      || s.includes('quota') || s.includes('resource_exhausted') || s.includes('resource exhausted')
      || s.includes('too many requests')
  }

  // ── 步骤状态 ──
  const activeStep = ref(1)
  const stepData = ref({})

  // ── Job 状态 ──
  const jobId = ref('')
  const jobStatus = ref('')
  const jobLog = ref([])
  const jobRunning = ref(false)
  const jobProgress = ref(0)
  const jobRecovery = ref(null)  // S2: recovery_hint

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

  // ── 引导式工作流可用性 ──
  const guidedAvailable = ref(true)

  // ── 计算属性 ──
  const stepLabels = computed(() => labels.workflow.steps)

  // ── Step 数据操作 ──

  async function loadStepData() {
    const appStore = useAppStore()
    if (!appStore.projectDir) return
    const data = await api.api('GET', '/api/status')
    if (data.error) {
      const raw = `${data.raw_error || data.error || ''}`.toLowerCase()
      if (raw.includes('method not allowed') || raw.includes('405') || raw.includes('not found') || raw.includes('404')) {
        guidedAvailable.value = false
      }
      return
    }
    guidedAvailable.value = true
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

    // 根据 step 状态推断文件 URL（后端 /api/status 不返回这些字段）
    _inferFileUrls(data.steps || [])
  }

  /** 根据 step 完成状态推断可用的文件 URL */
  function _inferFileUrls(stepsList) {
    const step6 = stepsList.find(s => s.n === 6) || {}
    const step7 = stepsList.find(s => s.n === 7) || {}
    if (!roughUrl.value && (step6.status === 'done' || step6.status === 'waiting_review')) {
      roughUrl.value = '/api/files/preview/rough_cut.mp4'
    }
    if (!finalUrl.value && step7.status === 'done') {
      finalUrl.value = '/api/files/output/final.mp4'
    }
  }

  async function runStep(step) {
    jobRunning.value = true
    jobStatus.value = ''
    jobLog.value = []
    jobProgress.value = 0
    jobRecovery.value = null

    const data = await api.api('POST', '/api/run_step', { render_opts: renderOpts.value })
    if (data.error) {
      jobRunning.value = false
      const raw = `${data.raw_error || data.error || ''}`.toLowerCase()
      if (raw.includes('method not allowed') || raw.includes('405') || raw.includes('not found') || raw.includes('404')) {
        guidedAvailable.value = false
        toast.show('引导式工作流服务暂未就绪，请使用「选题构思」等独立模块完成创作', 'warn', 6000)
      } else if (_isRateLimitError(data.raw_error || data.error)) {
        toast.show('AI 服务请求频率超限，请稍后重试', 'warn', 6000)
      } else {
        toast.show(data.error, 'danger')
      }
      return
    }

    jobId.value = data.job_id || ''
    if (jobId.value) {
      pollJob()
    }
  }

  async function approveStep(step) {
    const data = await api.api('POST', `/api/approve/${step}`)
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
      if (_isRateLimitError(data.error)) {
        toast.show('AI 服务请求频率超限，请稍后重试', 'warn', 6000)
      } else {
        toast.show(data.error, 'danger')
      }
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
      // S1: 渲染退化 Toast 通知
      _showDegradationToasts()
      return
    }
    if (status === 'error' || status === 'failed' || status === 'cancelled') {
      jobRunning.value = false
      jobRecovery.value = data.recovery || null
      if (status === 'cancelled') {
        toast.show('任务已取消', 'warn')
      } else if (_isRateLimitError(data.error)) {
        toast.show('AI 服务请求频率超限，请稍后重试', 'warn', 6000)
      } else {
        toast.show(data.error || '执行失败', 'danger')
      }
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

  /** S1: 渲染退化 Toast 通知 / S4: AI 退化通知 — 同时写入持久通知 */
  function _showDegradationToasts() {
    const appStore = useAppStore()
    const steps = appStore.steps || []
    // S1: render degradations (step 7)
    const step7 = steps.find(s => s.n === 7) || {}
    const degs = Array.isArray(step7.degradations) ? step7.degradations : []
    const typeMap = { error: 'danger', warning: 'warn', info: 'info' }
    for (const d of degs) {
      const t = typeMap[d.severity] || 'warn'
      const msg = `渲染退化: ${d.reason || d.feature || '未知'}`
      toast.show(msg, t, 8000)
      notifications.add({ message: msg, type: t, source: 'step7_render', details: d })
    }
    // S4: AI degradation (steps 2, 3)
    for (const n of [2, 3]) {
      const step = steps.find(s => s.n === n) || {}
      if (step.ai_degraded) {
        const msg = step.ai_degraded_reason || 'AI 生成已降级为模板模式'
        toast.show(msg, 'warn', 8000)
        notifications.add({ message: msg, type: 'warn', source: `step${n}_ai_degraded` })
      }
    }
  }

  /** S2: 智能重试 */
  async function retryWithRecovery() {
    const r = jobRecovery.value
    if (r && r.can_retry && r.retry_hint && r.retry_hint.endpoint) {
      if (r.duplicate_risk) {
        toast.show('注意: 重试可能产生重复发布，请确认', 'warn', 5000)
      }
      const data = await api.api('POST', r.retry_hint.endpoint, {})
      if (data.error) {
        toast.show(data.error, 'danger')
        return
      }
      if (data.job_id) {
        jobRunning.value = true
        jobStatus.value = ''
        jobLog.value = []
        jobProgress.value = 0
        jobRecovery.value = null
        jobId.value = data.job_id
        _pollTimer = setTimeout(() => pollJob(), 1500)
      } else {
        toast.show('重试已提交', 'success')
        jobStatus.value = ''
        jobRecovery.value = null
      }
    } else {
      // 无 recovery endpoint → 回退到普通重试
      const appStore = useAppStore()
      await runStep(appStore.currentStep)
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
    jobRecovery,
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
    guidedAvailable,
    stepLabels,
    loadStepData,
    runStep,
    approveStep,
    pollJob,
    cancelPoll,
    retryWithRecovery,
  }
})
