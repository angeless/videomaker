import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'
import { useProjectStore } from './project.js'
import { useSystemStore } from './system.js'
import { usePreferencesStore } from './preferences.js'

/**
 * App Store — 应用级编排器 + 向后兼容层。
 *
 * 实际状态拆分到 project / system / preferences 三个子 store，
 * 这里 re-export 所有属性供现有组件继续使用 `useAppStore()`。
 * 后续迁移组件直接引用子 store 后可逐步删除 re-export。
 */
export const useAppStore = defineStore('app', () => {
  const api = useApiStore()
  const projectStore = useProjectStore()
  const systemStore = useSystemStore()
  const prefsStore = usePreferencesStore()

  const loading = ref(true)
  const preflightAcknowledged = ref(false)
  const preflightErrorCount = computed(() => {
    const report = systemStore.preflightReport
    return report?.summary?.error || 0
  })

  // ── 向后兼容 re-export (project) ──
  const projectDir = computed({ get: () => projectStore.projectDir, set: v => { projectStore.projectDir = v } })
  const videosDir = computed({ get: () => projectStore.videosDir, set: v => { projectStore.videosDir = v } })
  const currentStep = computed({ get: () => projectStore.currentStep, set: v => { projectStore.currentStep = v } })
  const steps = computed({ get: () => projectStore.steps, set: v => { projectStore.steps = v } })
  const config = computed({ get: () => projectStore.config, set: v => { projectStore.config = v } })
  const showInit = computed({ get: () => projectStore.showInit, set: v => { projectStore.showInit = v } })
  const initMode = computed({ get: () => projectStore.initMode, set: v => { projectStore.initMode = v } })
  const initProjectName = computed({ get: () => projectStore.initProjectName, set: v => { projectStore.initProjectName = v } })
  const initVideosDir = computed({ get: () => projectStore.initVideosDir, set: v => { projectStore.initVideosDir = v } })
  const initProjectDir = computed({ get: () => projectStore.initProjectDir, set: v => { projectStore.initProjectDir = v } })
  const initOpenDir = computed({ get: () => projectStore.initOpenDir, set: v => { projectStore.initOpenDir = v } })
  const initLoading = computed({ get: () => projectStore.initLoading, set: v => { projectStore.initLoading = v } })
  const initError = computed({ get: () => projectStore.initError, set: v => { projectStore.initError = v } })
  const recentProjects = computed(() => projectStore.recentProjects)
  const recentProjectsLoading = computed(() => projectStore.recentProjectsLoading)
  const hasProject = computed(() => projectStore.hasProject)
  const ready = computed(() => projectStore.hasProject)

  // ── 向后兼容 re-export (system) ──
  const systemLoad = computed(() => systemStore.systemLoad)
  const runningHeavyJobs = computed(() => systemStore.runningHeavyJobs)
  const taskQueue = computed(() => systemStore.taskQueue)
  const preflightLoading = computed(() => systemStore.preflightLoading)
  const preflightMessage = computed(() => systemStore.preflightMessage)
  const preflightReport = computed(() => systemStore.preflightReport)
  const preflightLastRunAt = computed(() => systemStore.preflightLastRunAt)

  // ── 向后兼容 re-export (preferences) ──
  const uiSettings = computed({ get: () => prefsStore.uiSettings, set: v => { prefsStore.uiSettings = v } })
  const uiSettingsLoading = computed(() => prefsStore.uiSettingsLoading)
  const uiSettingsSaving = computed(() => prefsStore.uiSettingsSaving)
  const uiSettingsMessage = computed({ get: () => prefsStore.uiSettingsMessage, set: v => { prefsStore.uiSettingsMessage = v } })
  const showOnboardingWizard = computed({ get: () => prefsStore.showOnboardingWizard, set: v => { prefsStore.showOnboardingWizard = v } })

  // ── 方法代理 ──
  async function fetchStatus() {
    await projectStore.fetchStatus()
  }

  function applyState(data) {
    projectStore.applyState(data)
    systemStore.applySystemState(data)
  }

  async function runSystemPreflight(force = false) {
    return systemStore.runSystemPreflight(force)
  }

  async function refreshTaskQueue() {
    return systemStore.refreshTaskQueue()
  }

  async function loadUiSettings() {
    return prefsStore.loadUiSettings()
  }

  async function saveUiSettings() {
    return prefsStore.saveUiSettings()
  }

  function applyUiSettings() {
    prefsStore.applyUiSettings(projectStore)
  }

  async function dismissOnboarding(markCompleted = false) {
    return prefsStore.dismissOnboarding(markCompleted)
  }

  async function loadRecentProjects() {
    return projectStore.loadRecentProjects()
  }

  async function createProject(videosDir_, projectDir_, projectName_) {
    return projectStore.createProject(videosDir_, projectDir_, projectName_)
  }

  async function openProject(dir) {
    return projectStore.openProject(dir)
  }

  async function pickFolder(target) {
    // Handle preferences targets locally then delegate
    if (target === 'uiSettings.default_videos_dir') {
      const data = await api.api('POST', '/api/dialog/folder')
      if (data.path) prefsStore.uiSettings.default_videos_dir = data.path
      return
    }
    if (target === 'uiSettings.default_project_dir') {
      const data = await api.api('POST', '/api/dialog/folder')
      if (data.path) prefsStore.uiSettings.default_project_dir = data.path
      return
    }
    return projectStore.pickFolder(target)
  }

  async function pickFile(target) {
    return projectStore.pickFile(target)
  }

  // ── 初始化 ──
  async function initializeApp() {
    loading.value = true
    await api.bootstrap()
    await prefsStore.loadUiSettings()
    prefsStore.applyUiSettings(projectStore)
    await systemStore.runSystemPreflight(false)
    await projectStore.fetchStatus()
    loading.value = false

    if (!prefsStore.uiSettings.onboarding_completed) {
      prefsStore.showOnboardingWizard = true
    }
  }

  return {
    // state
    loading, preflightAcknowledged, preflightErrorCount,
    projectDir, videosDir, currentStep, steps, config,
    systemLoad, runningHeavyJobs, taskQueue,
    preflightLoading, preflightMessage, preflightReport, preflightLastRunAt,
    uiSettings, uiSettingsLoading, uiSettingsSaving, uiSettingsMessage,
    showOnboardingWizard,
    showInit, initMode, initProjectName, initVideosDir, initProjectDir, initOpenDir,
    initLoading, initError,
    recentProjects, recentProjectsLoading,
    // computed
    hasProject, ready,
    // methods
    fetchStatus, applyState,
    runSystemPreflight, refreshTaskQueue,
    loadUiSettings, saveUiSettings, applyUiSettings, dismissOnboarding,
    loadRecentProjects, createProject, openProject, pickFolder, pickFile,
    initializeApp,
  }
})
