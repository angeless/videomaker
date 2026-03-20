import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiStore } from './api.js'

export const useSettingsStore = defineStore('settings', () => {
  const api = useApiStore()

  // ── AI 配置 ──
  const aiSettings = ref({
    provider: 'openai',
    ai_model: '',
    embedding_model: '',
    ai_base_url: '',
    openai_api_key: '',
    anthropic_api_key: '',
    clear_openai_api_key: false,
    clear_anthropic_api_key: false,
  })

  const aiCatalog = ref({
    default_provider: 'openai',
    default_embedding_model: 'text-embedding-3-small',
    providers: [
      {
        provider_id: 'openai',
        label: 'OpenAI',
        default_base_url: 'https://api.openai.com/v1',
        models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'o4-mini', 'o3-mini'],
        embedding_models: ['text-embedding-3-small', 'text-embedding-3-large', 'text-embedding-ada-002'],
      },
      {
        provider_id: 'anthropic',
        label: 'Anthropic',
        default_base_url: 'https://api.anthropic.com',
        models: ['claude-sonnet-4-6', 'claude-3-7-sonnet-latest', 'claude-3-5-haiku-latest'],
        embedding_models: [],
      },
      {
        provider_id: 'moonshot',
        label: 'Moonshot / Kimi',
        default_base_url: 'https://api.moonshot.cn/v1',
        models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
        embedding_models: [],
      },
      {
        provider_id: 'qwen',
        label: 'Qwen',
        default_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        models: ['qwen-plus', 'qwen-turbo', 'qwen-max'],
        embedding_models: [],
      },
      {
        provider_id: 'gemini',
        label: 'Gemini',
        default_base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
        models: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
        embedding_models: [],
      },
    ],
  })

  const aiStatus = ref({
    openai_api_key_set: false,
    anthropic_api_key_set: false,
    openai_api_key_masked: '',
    anthropic_api_key_masked: '',
    secret_storage: { backend: '', available: false, reason: '' },
  })

  const aiLoading = ref(false)
  const aiSaving = ref(false)
  const aiMessage = ref('')

  // ── Helpers ──

  function _providerAlias(provider) {
    const p = `${provider || ''}`.trim().toLowerCase()
    if (p === 'kimi') return 'moonshot'
    if (p === 'minimax') return 'maxmini'
    return p
  }

  const providerOptions = computed(() => {
    const providers = aiCatalog.value?.providers
    if (Array.isArray(providers) && providers.length > 0) return providers
    return [{ provider_id: 'openai', label: 'OpenAI', default_base_url: 'https://api.openai.com/v1', models: [], embedding_models: [] }]
  })

  function _providerCatalog(provider = null) {
    const p = _providerAlias(provider || aiSettings.value.provider)
    return providerOptions.value.find(x => `${x.provider_id || ''}`.toLowerCase() === p) || null
  }

  function aiModelOptions(provider = null) {
    const item = _providerCatalog(provider)
    return (item?.models || []).filter(Boolean)
  }

  function embeddingModelOptions(provider = null) {
    const item = _providerCatalog(provider)
    return (item?.embedding_models || []).filter(Boolean)
  }

  const embeddingModelResolved = computed(() => {
    const current = `${aiSettings.value.embedding_model || ''}`.trim()
    if (current) return current
    return `${aiCatalog.value?.default_embedding_model || 'text-embedding-3-small'}`.trim()
  })

  function recommendedBaseUrl(provider = null, model = null) {
    const item = _providerCatalog(provider)
    if (!item) return ''
    const modelId = `${model || aiSettings.value.ai_model || ''}`.trim().toLowerCase()
    const modelBase = (item.model_base_urls && typeof item.model_base_urls === 'object') ? item.model_base_urls : {}
    if (modelId) {
      for (const [k, v] of Object.entries(modelBase)) {
        if (`${k || ''}`.trim().toLowerCase() === modelId && `${v || ''}`.trim()) return `${v || ''}`.trim()
      }
    }
    return `${item.default_base_url || ''}`.trim()
  }

  function onProviderChanged(forceModelSelection = false) {
    const provider = _providerAlias(aiSettings.value.provider)
    aiSettings.value.provider = provider || 'openai'
    const modelOpts = aiModelOptions(provider)
    const currentModel = `${aiSettings.value.ai_model || ''}`.trim()
    if (forceModelSelection && modelOpts.length > 0 && !currentModel) {
      aiSettings.value.ai_model = modelOpts[0]
    }
    const current = `${aiSettings.value.ai_base_url || ''}`.trim()
    const recommended = recommendedBaseUrl(provider, aiSettings.value.ai_model)
    if (!recommended) return
    const allRecommended = providerOptions.value
      .map(item => recommendedBaseUrl(item.provider_id, aiSettings.value.ai_model))
      .filter(Boolean)
    if (!current || allRecommended.includes(current)) {
      aiSettings.value.ai_base_url = recommended
    }
  }

  function onAiModelChanged() {
    const current = `${aiSettings.value.ai_base_url || ''}`.trim()
    const recommended = recommendedBaseUrl(aiSettings.value.provider, aiSettings.value.ai_model)
    if (!recommended) return
    const allRecommended = providerOptions.value
      .map(item => recommendedBaseUrl(item.provider_id, aiSettings.value.ai_model))
      .filter(Boolean)
    if (!current || allRecommended.includes(current)) {
      aiSettings.value.ai_base_url = recommended
    }
  }

  // ── API ──

  async function loadAiSettings() {
    aiLoading.value = true
    const data = await api.api('GET', '/api/settings/ai')
    aiLoading.value = false
    if (data.error) {
      aiMessage.value = `AI 配置读取失败：${data.error}`
      return
    }
    aiStatus.value = {
      openai_api_key_set: !!data.openai_api_key_set,
      anthropic_api_key_set: !!data.anthropic_api_key_set,
      openai_api_key_masked: data.openai_api_key_masked || '',
      anthropic_api_key_masked: data.anthropic_api_key_masked || '',
      secret_storage: data.secret_storage || { backend: '', available: false, reason: '' },
    }
    if (data.catalog?.providers) {
      aiCatalog.value = {
        default_provider: data.catalog.default_provider || 'openai',
        default_embedding_model: data.catalog.default_embedding_model || 'text-embedding-3-small',
        providers: data.catalog.providers,
      }
    }
    aiSettings.value.provider = data.provider || aiSettings.value.provider || 'openai'
    aiSettings.value.ai_model = data.ai_model || ''
    aiSettings.value.embedding_model = data.embedding_model || ''
    aiSettings.value.ai_base_url = data.ai_base_url || ''
    aiSettings.value.openai_api_key = ''
    aiSettings.value.anthropic_api_key = ''
    aiSettings.value.clear_openai_api_key = false
    aiSettings.value.clear_anthropic_api_key = false
    onProviderChanged(true)
    aiMessage.value = ''
  }

  async function saveAiSettings() {
    aiSaving.value = true
    aiMessage.value = ''
    const payload = {
      provider: aiSettings.value.provider || '',
      ai_model: aiSettings.value.ai_model || '',
      embedding_model: aiSettings.value.embedding_model || '',
      ai_base_url: aiSettings.value.ai_base_url || '',
      openai_api_key: aiSettings.value.openai_api_key || '',
      anthropic_api_key: aiSettings.value.anthropic_api_key || '',
      clear_openai_api_key: !!aiSettings.value.clear_openai_api_key,
      clear_anthropic_api_key: !!aiSettings.value.clear_anthropic_api_key,
    }
    const data = await api.api('POST', '/api/settings/ai', payload)
    aiSaving.value = false
    if (data.error) {
      aiMessage.value = `AI 配置保存失败：${data.error}`
      return
    }
    aiStatus.value = {
      openai_api_key_set: !!data.openai_api_key_set,
      anthropic_api_key_set: !!data.anthropic_api_key_set,
      openai_api_key_masked: data.openai_api_key_masked || '',
      anthropic_api_key_masked: data.anthropic_api_key_masked || '',
      secret_storage: data.secret_storage || { backend: '', available: false, reason: '' },
    }
    aiSettings.value.openai_api_key = ''
    aiSettings.value.anthropic_api_key = ''
    aiSettings.value.clear_openai_api_key = false
    aiSettings.value.clear_anthropic_api_key = false
    aiMessage.value = `AI 配置已保存。当前 Embedding 模型：${embeddingModelResolved.value}`
  }

  return {
    aiSettings,
    aiCatalog,
    aiStatus,
    aiLoading,
    aiSaving,
    aiMessage,
    providerOptions,
    embeddingModelResolved,
    aiModelOptions,
    embeddingModelOptions,
    recommendedBaseUrl,
    onProviderChanged,
    onAiModelChanged,
    loadAiSettings,
    saveAiSettings,
  }
})
