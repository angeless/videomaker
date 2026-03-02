import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiStore } from './api.js'
import { useToastStore } from './toast.js'
import labels from '../i18n/labels.js'

export const useCapabilitiesStore = defineStore('capabilities', () => {
  const api = useApiStore()
  const toast = useToastStore()

  const activeTab = ref('topic_library')
  const message = ref('')
  const messageType = ref('info')
  const loading = ref(false)

  // ── 工具组定义 ──
  const groups = ref([
    {
      key: 'creative',
      title: labels.tools.groups.creative,
      items: [
        { tab: 'topic_library', ...labels.tools.items.topic_library, mode: 'project' },
        { tab: 'topic_copy', ...labels.tools.items.topic_copy, mode: 'project' },
        { tab: 'text_rough', ...labels.tools.items.text_rough, mode: 'project' },
        { tab: 'short_clip', ...labels.tools.items.short_clip, mode: 'project' },
        { tab: 'refinement', ...labels.tools.items.refinement, mode: 'project' },
        { tab: 'audio_voice', ...labels.tools.items.audio_voice, mode: 'project' },
      ],
    },
    {
      key: 'semantics',
      title: labels.tools.groups.semantics,
      items: [
        { tab: 'subtitle_calibration', ...labels.tools.items.subtitle_calibration, mode: 'hybrid' },
        { tab: 'image_semantic', ...labels.tools.items.image_semantic, mode: 'hybrid' },
        { tab: 'article_expand', ...labels.tools.items.article_expand, mode: 'hybrid' },
        { tab: 'publish_prep', ...labels.tools.items.publish_prep, mode: 'hybrid' },
      ],
    },
    {
      key: 'distribution',
      title: labels.tools.groups.distribution,
      items: [
        { tab: 'social_export', ...labels.tools.items.social_export, mode: 'hybrid' },
        { tab: 'content_publish', ...labels.tools.items.content_publish, mode: 'hybrid' },
      ],
    },
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

  return {
    activeTab,
    message,
    messageType,
    loading,
    groups,
    setMessage,
    clearMessage,
  }
})
