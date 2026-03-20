import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiStore } from './api.js'

export const useSystemStore = defineStore('system', () => {
  const api = useApiStore()

  const systemLoad = ref(null)
  const runningHeavyJobs = ref([])

  // ── 中断任务恢复 ──
  const interruptedJobs = ref([])
  const interruptedLoading = ref(false)
  const interruptedBannerVisible = ref(false)

  async function loadInterruptedJobs() {
    interruptedLoading.value = true
    const data = await api.api('GET', '/api/job/interrupted')
    interruptedLoading.value = false
    if (data.error) return
    interruptedJobs.value = Array.isArray(data.jobs) ? data.jobs : []
    if (interruptedJobs.value.length > 0) {
      interruptedBannerVisible.value = true
    }
  }

  async function retryAllInterrupted(jobIds) {
    const ids = jobIds || interruptedJobs.value.map(j => j.job_id)
    const data = await api.api('POST', '/api/job/interrupted/retry-all', { job_ids: ids })
    if (!data.error) {
      interruptedJobs.value = interruptedJobs.value.filter(j => !ids.includes(j.job_id))
      if (interruptedJobs.value.length === 0) interruptedBannerVisible.value = false
    }
    return data
  }

  async function ignoreAllInterrupted(jobIds) {
    const ids = jobIds || interruptedJobs.value.map(j => j.job_id)
    const data = await api.api('POST', '/api/job/interrupted/ignore', { job_ids: ids })
    if (!data.error) {
      interruptedJobs.value = interruptedJobs.value.filter(j => !ids.includes(j.job_id))
      if (interruptedJobs.value.length === 0) interruptedBannerVisible.value = false
    }
    return data
  }

  function dismissInterruptedBanner() {
    interruptedBannerVisible.value = false
  }

  // ── 任务队列 ──
  const taskQueue = ref({
    max_running: 2,
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

  function applySystemState(data) {
    systemLoad.value = data.system || systemLoad.value
    runningHeavyJobs.value = data.running_jobs || []
    if (data.task_queue && typeof data.task_queue === 'object') {
      taskQueue.value = {
        max_running: Number(data.task_queue.max_running || taskQueue.value.max_running || 2),
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
        max_running: Number(data.task_queue.max_running || 2),
        running_count: Number(data.task_queue.running_count || 0),
        queued_count: Number(data.task_queue.queued_count || 0),
        running: Array.isArray(data.task_queue.running) ? data.task_queue.running : [],
        queued: Array.isArray(data.task_queue.queued) ? data.task_queue.queued : [],
      }
    }
  }

  return {
    systemLoad, runningHeavyJobs, taskQueue,
    interruptedJobs, interruptedLoading, interruptedBannerVisible,
    preflightLoading, preflightMessage, preflightReport, preflightLastRunAt,
    applySystemState, runSystemPreflight, refreshTaskQueue,
    loadInterruptedJobs, retryAllInterrupted, ignoreAllInterrupted, dismissInterruptedBanner,
  }
})
