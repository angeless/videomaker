import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'
import { useToastStore } from './toast.js'

export const useAppStore = defineStore('app', () => {
  const api = useApiStore()
  const toast = useToastStore()

  // ── 全局状态 ──
  const loading = ref(true)
  const projectDir = ref('')
  const videosDir = ref('')
  const currentStep = ref(0)
  const steps = ref([])
  const config = ref({})
  const systemLoad = ref(null)
  const runningHeavyJobs = ref([])

  // ── 任务队列 ──
  const taskQueue = ref({
    max_running: 1,
    running_count: 0,
    queued_count: 0,
    running: [],
    queued: [],
  })
  const _lastTaskQueueJson = ref('')

  // ── Preflight ──
  const preflightLoading = ref(false)
  const preflightMessage = ref('')
  const preflightReport = ref(null)
  const preflightLastRunAt = ref('')

  // ── UI Settings ──
  const uiSettings = ref({
    onboarding_completed: false,
    creator_mode: true,
    font_scale: 1.0,
    preferred_production_view: 'hub',
    default_videos_dir: '',
    default_project_dir: '',
    auto_open_last_project: true,
    last_project_dir: '',
  })
  const uiSettingsLoading = ref(false)
  const uiSettingsSaving = ref(false)
  const uiSettingsMessage = ref('')
  const showOnboardingWizard = ref(false)

  // ── 最近项目 ──
  const recentProjects = ref([])
  const recentProjectsLoading = ref(false)

  // ── 初始化/打开项目 ──
  const showInit = ref(false)
  const initMode = ref('new')
  const initVideosDir = ref('')
  const initProjectDir = ref('')
  const initOpenDir = ref('')
  const initLoading = ref(false)
  const initError = ref('')

  // ── 计算属性 ──
  const hasProject = computed(() => !!projectDir.value)

  // ── API Methods ──

  async function fetchStatus() {
    const data = await api.api('GET', '/api/status')
    if (data.ready) applyState(data)
  }

  function applyState(data) {
    projectDir.value = data.project_dir || ''
    videosDir.value = data.videos_dir || ''
    currentStep.value = data.current_step || 1
    steps.value = data.steps || []
    config.value = data.config || {}
    systemLoad.value = data.system || systemLoad.value
    runningHeavyJobs.value = data.running_jobs || []
    if (data.task_queue && typeof data.task_queue === 'object') {
      taskQueue.value = {
        max_running: Number(data.task_queue.max_running || taskQueue.value.max_running || 1),
        running_count: Number(data.task_queue.running_count || 0),
        queued_count: Number(data.task_queue.queued_count || 0),
        running: Array.isArray(data.task_queue.running) ? data.task_queue.running : [],
        queued: Array.isArray(data.task_queue.queued) ? data.task_queue.queued : [],
      }
    }
  }

  async function runSystemPreflight(force = false) {
    preflightLoading.value = true
    preflightMessage.value = ''
    const data = await api.api('GET', `/api/system/preflight${force ? '?force=1' : ''}`)
    preflightLoading.value = false
    if (data.error) {
      preflightMessage.value = `系统自检失败：${data.error}`
      return false
    }
    const report = (data.preflight && typeof data.preflight === 'object') ? data.preflight : null
    preflightReport.value = report
    preflightLastRunAt.value = report?.summary ? `${report.summary.generated_at || ''}` : ''
    if (!report) {
      preflightMessage.value = '系统自检返回空结果'
      return false
    }
    const summary = report.summary || {}
    preflightMessage.value = `自检完成：通过 ${summary.ok || 0}，警告 ${summary.warning || 0}，阻塞 ${summary.error || 0}`
    return (summary.error || 0) === 0
  }

  async function refreshTaskQueue() {
    const data = await api.api('GET', '/api/tasks/queue')
    if (data.error) return
    const incoming = JSON.stringify(data)
    if (incoming === _lastTaskQueueJson.value) return
    _lastTaskQueueJson.value = incoming
    if (data.task_queue) {
      taskQueue.value = {
        max_running: Number(data.task_queue.max_running || 1),
        running_count: Number(data.task_queue.running_count || 0),
        queued_count: Number(data.task_queue.queued_count || 0),
        running: Array.isArray(data.task_queue.running) ? data.task_queue.running : [],
        queued: Array.isArray(data.task_queue.queued) ? data.task_queue.queued : [],
      }
    }
  }

  // ── UI Settings Methods ──

  async function loadUiSettings() {
    uiSettingsLoading.value = true
    const data = await api.api('GET', '/api/settings/ui')
    uiSettingsLoading.value = false
    if (data.error) {
      uiSettingsMessage.value = `应用设置读取失败：${data.error}`
      return
    }
    uiSettings.value = {
      onboarding_completed: !!data.onboarding_completed,
      creator_mode: data.creator_mode !== false,
      font_scale: Number(data.font_scale || 1.0),
      preferred_production_view: `${data.preferred_production_view || 'hub'}`,
      default_videos_dir: data.default_videos_dir || '',
      default_project_dir: data.default_project_dir || '',
      auto_open_last_project: data.auto_open_last_project !== false,
      last_project_dir: data.last_project_dir || '',
    }
    uiSettingsMessage.value = ''
    applyUiSettings()
  }

  async function saveUiSettings() {
    uiSettingsSaving.value = true
    const payload = {
      onboarding_completed: !!uiSettings.value.onboarding_completed,
      creator_mode: !!uiSettings.value.creator_mode,
      font_scale: Number(uiSettings.value.font_scale || 1.0),
      preferred_production_view: uiSettings.value.preferred_production_view || 'hub',
      default_videos_dir: uiSettings.value.default_videos_dir || '',
      default_project_dir: uiSettings.value.default_project_dir || '',
      auto_open_last_project: !!uiSettings.value.auto_open_last_project,
    }
    const data = await api.api('POST', '/api/settings/ui', payload)
    uiSettingsSaving.value = false
    if (data.error) {
      uiSettingsMessage.value = `应用设置保存失败：${data.error}`
      return
    }
    await loadUiSettings()
    uiSettingsMessage.value = '应用设置已保存'
  }

  function applyUiSettings() {
    const scale = Math.max(0.85, Math.min(Number(uiSettings.value.font_scale || 1), 1.45))
    uiSettings.value.font_scale = Number.isFinite(scale) ? Number(scale.toFixed(2)) : 1.0
    document.body.style.zoom = `${uiSettings.value.font_scale}`
    if (!initVideosDir.value && uiSettings.value.default_videos_dir) {
      initVideosDir.value = uiSettings.value.default_videos_dir
    }
    if (!initProjectDir.value && uiSettings.value.default_project_dir) {
      initProjectDir.value = uiSettings.value.default_project_dir
    }
  }

  async function dismissOnboarding(markCompleted = false) {
    showOnboardingWizard.value = false
    if (!markCompleted) return
    uiSettings.value.onboarding_completed = true
    await saveUiSettings()
  }

  // ── 最近项目 ──

  async function loadRecentProjects() {
    recentProjectsLoading.value = true
    const data = await api.api('GET', '/api/project/list')
    recentProjectsLoading.value = false
    if (data.error) return
    recentProjects.value = data.projects || []
  }

  // ── 项目操作 ──

  async function createProject(videosDir_, projectDir_) {
    initLoading.value = true
    initError.value = ''
    const data = await api.api('POST', '/api/project/create', {
      videos_dir: videosDir_,
      project_dir: projectDir_,
    })
    initLoading.value = false
    if (data.error) {
      initError.value = data.error
      return false
    }
    await fetchStatus()
    showInit.value = false
    return true
  }

  async function openProject(dir) {
    initLoading.value = true
    initError.value = ''
    const data = await api.api('POST', '/api/project/open', { project_dir: dir })
    initLoading.value = false
    if (data.error) {
      initError.value = data.error
      return false
    }
    await fetchStatus()
    showInit.value = false
    return true
  }

  async function pickFolder(target) {
    const data = await api.api('POST', '/api/dialog/folder')
    if (data.path) {
      // 支持嵌套路径写入
      if (target === 'initVideosDir') initVideosDir.value = data.path
      else if (target === 'initProjectDir') initProjectDir.value = data.path
      else if (target === 'initOpenDir') initOpenDir.value = data.path
      else if (target === 'uiSettings.default_videos_dir') uiSettings.value.default_videos_dir = data.path
      else if (target === 'uiSettings.default_project_dir') uiSettings.value.default_project_dir = data.path
    } else if (data.error && !data.cancelled) {
      toast.show(`选择文件夹失败：${data.error}`, 'danger')
    }
  }

  async function pickFile(target) {
    const data = await api.api('POST', '/api/dialog/file')
    if (data.path) {
      return data.path
    }
    if (data.error && !data.cancelled) {
      toast.show(`选择文件失败：${data.error}`, 'danger')
    }
    return ''
  }

  // ── 初始化应用 ──

  async function initializeApp() {
    loading.value = true
    await api.bootstrap()
    await loadUiSettings()
    await runSystemPreflight(false)
    await fetchStatus()
    loading.value = false

    if (!uiSettings.value.onboarding_completed) {
      showOnboardingWizard.value = true
    }
  }

  return {
    // state
    loading,
    projectDir,
    videosDir,
    currentStep,
    steps,
    config,
    systemLoad,
    runningHeavyJobs,
    taskQueue,
    preflightLoading,
    preflightMessage,
    preflightReport,
    preflightLastRunAt,
    uiSettings,
    uiSettingsLoading,
    uiSettingsSaving,
    uiSettingsMessage,
    showOnboardingWizard,
    showInit,
    initMode,
    initVideosDir,
    initProjectDir,
    initOpenDir,
    initLoading,
    initError,
    recentProjects,
    recentProjectsLoading,
    // computed
    hasProject,
    // methods
    fetchStatus,
    applyState,
    runSystemPreflight,
    refreshTaskQueue,
    loadUiSettings,
    saveUiSettings,
    applyUiSettings,
    dismissOnboarding,
    loadRecentProjects,
    createProject,
    openProject,
    pickFolder,
    pickFile,
    initializeApp,
  }
})
