import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 持久通知 store — 降级、错误等需要用户知晓的信息。
 * 与 toast（4-8 秒自动消失）不同，这里的通知持久保存直到用户手动标记已读。
 */
export const useNotificationsStore = defineStore('notifications', () => {
  const items = ref([])

  const unreadCount = computed(() => items.value.filter(n => !n.read).length)

  /**
   * 添加通知
   * @param {object} opts
   * @param {string} opts.message - 通知内容
   * @param {'info'|'warn'|'danger'} opts.type - 通知类型
   * @param {string} [opts.source] - 来源（如 'step7_render', 'step2_topic'）
   * @param {object} [opts.details] - 附加详情（feature, severity 等）
   */
  function add({ message, type = 'info', source = '', details = null }) {
    items.value.unshift({
      id: Date.now() + Math.random(),
      message,
      type,
      source,
      details,
      timestamp: new Date().toISOString(),
      read: false,
    })
  }

  function markRead(id) {
    const item = items.value.find(n => n.id === id)
    if (item) item.read = true
  }

  function markAllRead() {
    items.value.forEach(n => { n.read = true })
  }

  function remove(id) {
    items.value = items.value.filter(n => n.id !== id)
  }

  function clear() {
    items.value = []
  }

  return { items, unreadCount, add, markRead, markAllRead, remove, clear }
})
