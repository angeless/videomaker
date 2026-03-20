import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiStore } from './api.js'

export const usePreferencesStore = defineStore('preferences', () => {
  const api = useApiStore()

  const uiSettings = ref({
    onboarding_completed: false,
    onboarding_step: 0,
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
      onboarding_step: parseInt(data.onboarding_step, 10) || 0,
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
      onboarding_step: uiSettings.value.onboarding_step || 0,
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

  function applyUiSettings(projectStore = null) {
    const scale = Math.max(0.85, Math.min(Number(uiSettings.value.font_scale || 1), 1.45))
    uiSettings.value.font_scale = Number.isFinite(scale) ? Number(scale.toFixed(2)) : 1.0
    document.body.style.zoom = `${uiSettings.value.font_scale}`
    if (projectStore) {
      if (!projectStore.initVideosDir && uiSettings.value.default_videos_dir) {
        projectStore.initVideosDir = uiSettings.value.default_videos_dir
      }
      if (!projectStore.initProjectDir && uiSettings.value.default_project_dir) {
        projectStore.initProjectDir = uiSettings.value.default_project_dir
      }
    }
  }

  async function dismissOnboarding(markCompleted = false) {
    showOnboardingWizard.value = false
    if (!markCompleted) return
    uiSettings.value.onboarding_completed = true
    await saveUiSettings()
  }

  return {
    uiSettings, uiSettingsLoading, uiSettingsSaving, uiSettingsMessage,
    showOnboardingWizard,
    loadUiSettings, saveUiSettings, applyUiSettings, dismissOnboarding,
  }
})
