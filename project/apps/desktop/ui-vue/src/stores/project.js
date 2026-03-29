import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'
import { useToastStore } from './toast.js'

export const useProjectStore = defineStore('project', () => {
  const api = useApiStore()
  const toast = useToastStore()

  // 从 localStorage 恢复项目路径，避免页面刷新丢失上下文
  const _savedProjectDir = typeof localStorage !== 'undefined'
    ? localStorage.getItem('videoeditor_projectDir') || ''
    : ''
  const projectDir = ref(_savedProjectDir)
  const videosDir = ref('')
  const currentStep = ref(0)
  const steps = ref([])
  const config = ref({})

  // ── 初始化/打开项目 ──
  const showInit = ref(false)
  const initMode = ref('new')
  const initProjectName = ref('')
  const initVideosDir = ref('')
  const initProjectDir = ref('')
  const initOpenDir = ref('')
  const initLoading = ref(false)
  const initError = ref('')

  // ── 最近项目 ──
  const recentProjects = ref([])
  const recentProjectsLoading = ref(false)

  // ── 项目元数据（T-0604）──
  const projectDisplayName = ref('')
  const projectMeta = ref({})

  const hasProject = computed(() => !!projectDir.value)

  async function fetchStatus() {
    const data = await api.api('GET', '/api/status')
    if (data.error) {
      // Network or server failure — clear state, show fallback
      _clearProjectState()
      return
    }
    if (data.ready) {
      applyState(data)
      loadProjectMeta()
    } else if (_savedProjectDir) {
      // 后端未返回项目但本地有缓存 → 尝试重新打开
      const reopen = await api.api('POST', '/api/open_project', { project_dir: _savedProjectDir })
      if (!reopen.error) {
        const data2 = await api.api('GET', '/api/status')
        if (data2.ready) {
          applyState(data2)
          loadProjectMeta()
          return
        }
      }
      // Reopen failed — clear stale local cache
      _clearProjectState()
    } else {
      _clearProjectState()
    }
  }

  function _clearProjectState() {
    projectDir.value = ''
    videosDir.value = ''
    currentStep.value = 0
    steps.value = []
    config.value = {}
    projectDisplayName.value = ''
    projectMeta.value = {}
    try { localStorage.removeItem('videoeditor_projectDir') } catch {}
  }

  function applyState(data) {
    projectDir.value = data.project_dir || ''
    videosDir.value = data.videos_dir || ''
    currentStep.value = data.current_step || 1
    steps.value = data.steps || []
    config.value = data.config || {}
    // 持久化到 localStorage
    if (projectDir.value) {
      try { localStorage.setItem('videoeditor_projectDir', projectDir.value) } catch {}
    }
  }

  async function loadRecentProjects() {
    recentProjectsLoading.value = true
    const data = await api.api('GET', '/api/project/list')
    recentProjectsLoading.value = false
    if (data.error) return
    recentProjects.value = data.projects || []
  }

  async function createProject(videosDir_, projectDir_, projectName_) {
    initLoading.value = true
    initError.value = ''
    const body = { videos_dir: videosDir_, project_dir: projectDir_ }
    if (projectName_) body.project_name = projectName_
    const data = await api.api('POST', '/api/init', body)
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
    const data = await api.api('POST', '/api/open_project', { project_dir: dir })
    initLoading.value = false
    if (data.error) {
      initError.value = data.error
      return false
    }
    await fetchStatus()
    showInit.value = false
    return true
  }

  async function loadProjectMeta() {
    if (!projectDir.value) return
    const data = await api.api('GET', `/api/project/meta?project_dir=${encodeURIComponent(projectDir.value)}`)
    if (data.ok && data.meta) {
      projectMeta.value = data.meta
      projectDisplayName.value = data.meta.display_name || ''
    }
  }

  async function renameProject(newName) {
    if (!projectDir.value) return false
    const data = await api.api('POST', '/api/project/rename', {
      project_dir: projectDir.value,
      display_name: newName,
    })
    if (data.error) {
      toast.show(data.error, 'danger')
      return false
    }
    if (data.ok && data.meta) {
      projectMeta.value = data.meta
      projectDisplayName.value = data.meta.display_name || ''
    }
    return true
  }

  async function pickFolder(target) {
    const data = await api.api('POST', '/api/dialog/folder')
    if (data.path) {
      if (target === 'initVideosDir') initVideosDir.value = data.path
      else if (target === 'initProjectDir') initProjectDir.value = data.path
      else if (target === 'initOpenDir') initOpenDir.value = data.path
      else return data.path
    } else if (data.error && !data.cancelled) {
      toast.show(`选择文件夹失败：${data.error}`, 'danger')
    }
  }

  async function pickFile(target) {
    const data = await api.api('POST', '/api/dialog/file')
    if (data.path) return data.path
    if (data.error && !data.cancelled) {
      toast.show(`选择文件失败：${data.error}`, 'danger')
    }
    return ''
  }

  return {
    projectDir, videosDir, currentStep, steps, config,
    projectDisplayName, projectMeta,
    showInit, initMode, initProjectName, initVideosDir, initProjectDir, initOpenDir,
    initLoading, initError, recentProjects, recentProjectsLoading,
    hasProject,
    fetchStatus, applyState, loadRecentProjects, loadProjectMeta, renameProject,
    createProject, openProject, pickFolder, pickFile,
  }
})
