/**
 * 格式化工具
 */

export function useFormatters() {
  function formatDuration(seconds) {
    const s = Number(seconds) || 0
    if (s < 60) return `${Math.round(s)}秒`
    const m = Math.floor(s / 60)
    const sec = Math.round(s % 60)
    return `${m}分${sec}秒`
  }

  function formatFileSize(bytes) {
    const b = Number(bytes) || 0
    if (b < 1024) return `${b} B`
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
    if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`
    return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  function formatDate(dateStr) {
    if (!dateStr) return ''
    try {
      const d = new Date(dateStr)
      return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    } catch {
      return dateStr
    }
  }

  /**
   * normalizeTemplateId: 从 common_utils_mixin.js 迁移
   */
  function normalizeTemplateId(value) {
    const text = `${value || ''}`.trim().toLowerCase()
    if (!text) return ''
    let out = ''
    for (const ch of text) {
      if ((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch === '_') out += ch
      else if (ch === '-' || ch === ' ' || ch === '/') out += '_'
    }
    while (out.includes('__')) out = out.replace(/__+/g, '_')
    return out.replace(/^_+|_+$/g, '').slice(0, 64)
  }

  /**
   * parseSpanIndexExpr: 从 common_utils_mixin.js 迁移
   */
  function parseSpanIndexExpr(value, maxIndex = 0) {
    const text = `${value || ''}`.trim()
    if (!text) return []
    const normalized = text.replace(/[，；;、\s]+/g, ',')
    const out = new Set()
    const maxN = Number(maxIndex || 0)
    for (const token of normalized.split(',')) {
      const part = `${token || ''}`.trim()
      if (!part) continue
      if (part.includes('-')) {
        const [leftRaw, rightRaw] = part.split('-', 2)
        const left = parseInt(leftRaw, 10)
        const right = parseInt(rightRaw, 10)
        if (!Number.isFinite(left) || !Number.isFinite(right)) continue
        let lo = Math.max(Math.min(left, right), 1)
        let hi = Math.max(left, right)
        if (maxN > 0) hi = Math.min(hi, maxN)
        if (hi < lo) continue
        for (let i = lo; i <= hi; i += 1) out.add(i)
        continue
      }
      const idx = parseInt(part, 10)
      if (!Number.isFinite(idx) || idx <= 0) continue
      if (maxN > 0 && idx > maxN) continue
      out.add(idx)
    }
    return Array.from(out).sort((a, b) => a - b)
  }

  function formatSpanIndexExpr(indexes) {
    const arr = Array.isArray(indexes)
      ? indexes.map(x => parseInt(x, 10)).filter(x => Number.isFinite(x) && x > 0).sort((a, b) => a - b)
      : []
    if (!arr.length) return ''
    const parts = []
    let start = arr[0]
    let prev = arr[0]
    for (let i = 1; i < arr.length; i += 1) {
      const cur = arr[i]
      if (cur === prev || cur === prev + 1) {
        prev = cur
        continue
      }
      parts.push(start === prev ? `${start}` : `${start}-${prev}`)
      start = cur
      prev = cur
    }
    parts.push(start === prev ? `${start}` : `${start}-${prev}`)
    return parts.join(',')
  }

  /**
   * humanizeProjectDir: 将项目路径转为可读显示名
   */
  function humanizeProjectDir(dir) {
    if (!dir) return '未打开项目'
    const name = dir.split('/').filter(Boolean).pop() || dir
    const m = name.match(/^proj_selected_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/)
    if (m) return `项目 ${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`
    return name
  }

  return {
    formatDuration,
    formatFileSize,
    formatDate,
    humanizeProjectDir,
    normalizeTemplateId,
    parseSpanIndexExpr,
    formatSpanIndexExpr,
  }
}
