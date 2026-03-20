import { ref, onUnmounted } from 'vue'
import { useApiStore } from '../stores/api.js'

/**
 * 通用任务轮询 composable
 * @param {Object} options
 * @param {Function} options.onProgress - 进度回调
 * @param {Function} options.onComplete - 完成回调
 * @param {Function} options.onError - 错误回调
 * @param {number} options.interval - 轮询间隔（ms），默认 1500
 */
export function useJobPoller(options = {}) {
  const api = useApiStore()
  const jobId = ref('')
  const status = ref('')
  const progress = ref(0)
  const log = ref([])
  const running = ref(false)

  let timer = null
  let lastJson = ''

  async function startPolling(id) {
    jobId.value = id
    running.value = true
    status.value = ''
    progress.value = 0
    log.value = []
    lastJson = ''
    await poll()
  }

  async function poll() {
    if (!jobId.value || !running.value) return

    const data = await api.api('GET', `/api/job/${jobId.value}`)
    if (data.error) {
      running.value = false
      options.onError?.(data.error)
      return
    }

    // JSON diff guard
    const incoming = JSON.stringify(data)
    if (incoming !== lastJson) {
      lastJson = incoming
      status.value = data.status || ''
      progress.value = data.progress || 0
      if (Array.isArray(data.log)) {
        log.value = data.log
      }
      options.onProgress?.(data)
    }

    const st = `${data.status || ''}`.toLowerCase()
    if (st === 'completed' || st === 'done') {
      running.value = false
      options.onComplete?.(data)
      return
    }
    if (st === 'error' || st === 'failed') {
      running.value = false
      options.onError?.(data.error || '执行失败')
      return
    }

    timer = setTimeout(() => poll(), options.interval || 1500)
  }

  function stopPolling() {
    running.value = false
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  onUnmounted(() => {
    stopPolling()
  })

  return {
    jobId,
    status,
    progress,
    log,
    running,
    startPolling,
    stopPolling,
  }
}
