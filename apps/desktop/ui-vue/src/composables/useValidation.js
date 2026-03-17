import { reactive, computed } from 'vue'

/**
 * 表单校验 composable
 *
 * @param {Object} rules — { fieldName: [{ type, message, ...params }] }
 *
 * 内置规则类型：
 *   required      — 不能为空（空字符串、null、undefined、空数组）
 *   minLength(n)  — 字符串最短长度
 *   maxLength(n)  — 字符串最长长度
 *   url           — 必须是合法 URL
 *   range(min,max)— 数值范围
 *   pattern(re)   — 正则表达式
 *   minItems(n)   — 数组最少元素数
 */
export function useValidation(rules) {
  const errors = reactive({})
  const touched = reactive({})

  // 初始化
  for (const field of Object.keys(rules)) {
    errors[field] = ''
    touched[field] = false
  }

  function _check(rule, value) {
    switch (rule.type) {
      case 'required': {
        if (value === null || value === undefined) return rule.message
        if (typeof value === 'string' && value.trim() === '') return rule.message
        if (Array.isArray(value) && value.length === 0) return rule.message
        return ''
      }
      case 'minLength': {
        if (typeof value === 'string' && value.length < rule.min) return rule.message
        return ''
      }
      case 'maxLength': {
        if (typeof value === 'string' && value.length > rule.max) return rule.message
        return ''
      }
      case 'url': {
        if (!value) return '' // 空值由 required 管
        try {
          new URL(value)
          return ''
        } catch {
          return rule.message
        }
      }
      case 'range': {
        const n = Number(value)
        if (isNaN(n)) return rule.message
        if (n < rule.min || n > rule.max) return rule.message
        return ''
      }
      case 'pattern': {
        if (!value) return ''
        const re = rule.pattern instanceof RegExp ? rule.pattern : new RegExp(rule.pattern)
        if (!re.test(value)) return rule.message
        return ''
      }
      case 'minItems': {
        if (!Array.isArray(value) || value.length < rule.min) return rule.message
        return ''
      }
      default:
        return ''
    }
  }

  function validate(field, value) {
    touched[field] = true
    const fieldRules = rules[field] || []
    for (const rule of fieldRules) {
      const err = _check(rule, value)
      if (err) {
        errors[field] = err
        return false
      }
    }
    errors[field] = ''
    return true
  }

  function validateAll(values) {
    let allValid = true
    for (const field of Object.keys(rules)) {
      const ok = validate(field, values[field])
      if (!ok) allValid = false
    }
    return allValid
  }

  function touch(field) {
    touched[field] = true
  }

  function getError(field) {
    return touched[field] ? errors[field] : ''
  }

  const isValid = computed(() => {
    return Object.values(errors).every(e => !e)
  })

  return { errors, touched, validate, validateAll, isValid, getError, touch }
}
