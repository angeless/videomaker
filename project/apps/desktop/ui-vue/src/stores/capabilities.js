import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiStore } from './api.js'
import { useToastStore } from './toast.js'
import { useAppStore } from './app.js'
import labels from '../i18n/labels.js'

export const useCapabilitiesStore = defineStore('capabilities', () => {
  const api = useApiStore()
  const toast = useToastStore()

  const activeTab = ref('topic_library')
  const message = ref('')
  const messageType = ref('info')
  const loading = ref(false)
  const statuses = ref({})

  // ── 工具组定义（旅程导向分组） ──
  const groups = ref([
    {
      key: 'content',
      title: labels.tools.groups.content,
      items: [
        { tab: 'topic_library', ...labels.tools.items.topic_library, mode: 'project' },
        { tab: 'topic_copy', ...labels.tools.items.topic_copy, mode: 'project' },
        { tab: 'article_expand', ...labels.tools.items.article_expand, mode: 'hybrid' },
      ],
    },
    {
      key: 'editing',
      title: labels.tools.groups.editing,
      items: [
        { tab: 'text_rough', ...labels.tools.items.text_rough, mode: 'project' },
        { tab: 'short_clip', ...labels.tools.items.short_clip, mode: 'project' },
        { tab: 'refinement', ...labels.tools.items.refinement, mode: 'project' },
      ],
    },
    {
      key: 'enhance',
      title: labels.tools.groups.enhance,
      items: [
        { tab: 'audio_voice', ...labels.tools.items.audio_voice, mode: 'project' },
        { tab: 'subtitle_calibration', ...labels.tools.items.subtitle_calibration, mode: 'hybrid' },
        { tab: 'image_semantic', ...labels.tools.items.image_semantic, mode: 'hybrid' },
      ],
    },
    {
      key: 'distribute',
      title: labels.tools.groups.distribute,
      items: [
        { tab: 'publish_prep', ...labels.tools.items.publish_prep, mode: 'hybrid' },
        { tab: 'social_export', ...labels.tools.items.social_export, mode: 'hybrid' },
        { tab: 'content_publish', ...labels.tools.items.content_publish, mode: 'hybrid' },
      ],
    },
  ])

  // ── 系统工具组（仅在 /tools 路由展示） ──
  const systemGroups = ref([
    {
      key: 'automation',
      title: labels.tools.groups.automation,
      items: [
        { tab: 'workflow_builder', ...labels.tools.items.workflow_builder, mode: 'hybrid' },
        { tab: 'idempotency_cache', ...labels.tools.items.idempotency_cache, mode: 'hybrid' },
        { tab: 'agent_templates', ...labels.tools.items.agent_templates, mode: 'hybrid' },
        { tab: 'agent_observability', ...labels.tools.items.agent_observability, mode: 'hybrid' },
      ],
    },
  ])

  function setMessage(msg, type = 'info') {
    message.value = msg
    messageType.value = type
  }

  function clearMessage() {
    message.value = ''
    messageType.value = 'info'
  }

  async function loadStatuses() {
    const data = await api.api('GET', '/api/capabilities')
    if (data.error) return
    const map = {}
    for (const spec of (data.capabilities || [])) {
      if (spec.capability_id) map[spec.capability_id] = spec.status || 'planned'
    }
    if (map.text_rough_cut && !map.text_rough) map.text_rough = map.text_rough_cut
    statuses.value = map
  }

  function _findItem(tab) {
    for (const g of [...groups.value, ...systemGroups.value]) {
      const item = g.items.find(i => i.tab === tab)
      if (item) return item
    }
    return null
  }

  function isExecutable(tab) {
    const appStore = useAppStore()
    const item = _findItem(tab)
    if (!item) return false
    if (item.mode === 'project' && !appStore.ready) return false
    return true
  }

  function executionHint(tab) {
    const appStore = useAppStore()
    const item = _findItem(tab)
    if (!item) return ''
    if (item.mode === 'project' && !appStore.ready) return '需先打开项目'
    return ''
  }

  function statusText(tab) {
    const hint = executionHint(tab)
    if (hint) return hint
    const s = statuses.value[tab]
    if (s === 'ready') return '稳定'
    if (s === 'prototype') return '可用'
    if (s === 'planned') return '开发中'
    return ''
  }

  function statusClass(tab) {
    if (executionHint(tab)) return 'badge-warn'
    const s = statuses.value[tab]
    if (s === 'ready') return 'badge-success'
    if (s === 'prototype') return 'badge-info'
    if (s === 'planned') return 'badge-muted'
    return ''
  }

  return {
    activeTab,
    message,
    messageType,
    loading,
    groups,
    systemGroups,
    statuses,
    setMessage,
    clearMessage,
    loadStatuses,
    isExecutable,
    executionHint,
    statusText,
    statusClass,
  }
})
