import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useApiStore = defineStore('api', () => {
  const token = ref('')
  const csrfToken = ref('')
  const sessionReady = ref(false)
  const authRequired = ref(false)

  function friendlyErrorMessage(rawError) {
    const text = `${rawError || ''}`.trim()
    if (!text) return '请求失败，请稍后重试。'
    const lowered = text.toLowerCase()
    if (lowered.includes('traceback')) {
      return '系统执行异常。请重试；若持续失败，请在应用设置中导出日志后反馈。'
    }
    if (lowered.includes('no module named')) {
      return '运行环境缺少依赖。请重启应用，启动器会自动补齐依赖。'
    }
    if (lowered.includes('413') || lowered.includes('请求内容过大')) {
      return '本次提交内容过大，请拆成多次执行。'
    }
    if (lowered.includes('api key') || lowered.includes('unauthorized')) {
      return 'AI Key 未配置或无效，请先在 AI 配置中保存有效 Key。'
    }
    if (lowered.includes('csrf') || lowered.includes('安全校验')) {
      return '安全校验已过期，请刷新应用后重试。'
    }
    if (lowered.includes('非法来源') || lowered.includes('origin_forbidden')) {
      return '当前请求来源不被允许，请在应用内操作。'
    }
    if (text.length > 300) {
      return '操作失败（已截断技术细节）。请重试或查看诊断日志。'
    }
    return text
  }

  async function bootstrap() {
    try {
      const res = await fetch('/api/session/bootstrap', { method: 'GET' })
      const text = await res.text()
      let data = {}
      try { data = text ? JSON.parse(text) : {} } catch { data = {} }
      if (!res.ok || data.error) {
        sessionReady.value = false
        return false
      }
      token.value = `${data.token || ''}`.trim()
      csrfToken.value = `${data.csrf_token || ''}`.trim()
      authRequired.value = !!data.auth_required
      sessionReady.value = true
      return true
    } catch {
      sessionReady.value = false
      return false
    }
  }

  async function api(method, path, body, _retried = false) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } }
    if (token.value) {
      opts.headers['X-VideoEditor-Token'] = token.value
    }
    const upperMethod = `${method || 'GET'}`.toUpperCase()
    if (csrfToken.value && !['GET', 'HEAD', 'OPTIONS'].includes(upperMethod)) {
      opts.headers['X-VideoEditor-CSRF'] = csrfToken.value
    }
    if (body !== undefined) opts.body = JSON.stringify(body)
    try {
      const res = await fetch(path, opts)
      const text = await res.text()
      let data = {}
      try { data = text ? JSON.parse(text) : {} } catch { data = { error: text || '服务端返回非 JSON 响应' } }
      if (!res.ok && !data.error) {
        data.error = `请求失败（HTTP ${res.status}）`
      }
      const code = `${data.code || ''}`.trim()
      if (res.status === 401 && code === 'local_auth_required' && !_retried) {
        const ok = await bootstrap()
        if (ok) return api(method, path, body, true)
      }
      if (res.status === 403 && code === 'csrf_required' && !_retried) {
        const ok = await bootstrap()
        if (ok) return api(method, path, body, true)
      }
      if (data.error) {
        data.raw_error = data.error
        data.error = friendlyErrorMessage(data.error)
      }
      return data
    } catch (err) {
      return { error: `请求失败：${err && err.message ? err.message : '网络异常'}` }
    }
  }

  return {
    token,
    csrfToken,
    sessionReady,
    authRequired,
    bootstrap,
    api,
    friendlyErrorMessage,
  }
})
