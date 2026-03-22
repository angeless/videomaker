<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <ProjectTitle />
    <AppNav />
  </div>

  <div class="main">
    <div class="content">
      <div class="content-narrow">
        <h2 style="margin-bottom: 24px">{{ labels.settings.title }}</h2>

        <!-- AI 配置 -->
        <div class="card">
          <div class="card-header">🤖 {{ labels.settings.ai.title }}</div>

          <div class="form-group">
            <label class="form-label">{{ labels.settings.ai.provider }}</label>
            <select v-model="settings.aiSettings.provider" class="form-select" @change="settings.onProviderChanged()">
              <option v-for="p in settings.providerOptions" :key="p.provider_id" :value="p.provider_id">
                {{ p.label }}
              </option>
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">{{ labels.settings.ai.model }}</label>
            <select v-model="settings.aiSettings.ai_model" class="form-select" @change="settings.onAiModelChanged()">
              <option value="">（自动选择）</option>
              <option v-for="m in settings.aiModelOptions()" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">{{ labels.settings.ai.embeddingModel }}</label>
            <select v-model="settings.aiSettings.embedding_model" class="form-select">
              <option value="">默认（{{ settings.embeddingModelResolved }}）</option>
              <option v-for="m in settings.embeddingModelOptions()" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>

          <FormField
            :label="labels.settings.ai.baseUrl"
            :error="v.getError('ai_base_url')"
          >
            <div class="form-row">
              <input
                v-model="settings.aiSettings.ai_base_url"
                class="form-input"
                placeholder="https://api.openai.com/v1"
                @blur="v.validate('ai_base_url', settings.aiSettings.ai_base_url)"
              />
              <button class="btn btn-ghost btn-sm" @click="fillUrl">{{ labels.settings.ai.fillUrl }}</button>
            </div>
          </FormField>

          <div class="form-group">
            <label class="form-label">OpenAI 密钥</label>
            <div class="form-row">
              <input
                v-model="settings.aiSettings.openai_api_key"
                class="form-input"
                type="password"
                placeholder="sk-..."
              />
              <span class="badge" :class="settings.aiStatus.openai_api_key_set ? 'badge-success' : 'badge-warn'">
                {{ settings.aiStatus.openai_api_key_set ? labels.settings.ai.keyMasked : labels.settings.ai.keyNotSet }}
              </span>
            </div>
            <div class="form-hint">用于 AI 选题、脚本生成和语义搜索</div>
          </div>

          <div class="form-group">
            <label class="form-label">Anthropic 密钥</label>
            <div class="form-row">
              <input
                v-model="settings.aiSettings.anthropic_api_key"
                class="form-input"
                type="password"
                placeholder="sk-ant-..."
              />
              <span class="badge" :class="settings.aiStatus.anthropic_api_key_set ? 'badge-success' : 'badge-warn'">
                {{ settings.aiStatus.anthropic_api_key_set ? labels.settings.ai.keyMasked : labels.settings.ai.keyNotSet }}
              </span>
            </div>
            <div class="form-hint">可选，作为备用 AI 服务商</div>
          </div>

          <div v-if="settings.aiMessage" class="badge badge-info" style="margin-bottom: 12px">
            {{ settings.aiMessage }}
          </div>

          <div style="display: flex; gap: 8px; align-items: center">
            <button class="btn btn-primary" :disabled="settings.aiSaving" @click="settings.saveAiSettings()">
              {{ settings.aiSaving ? labels.settings.ai.saving : labels.settings.ai.save }}
            </button>
            <button class="btn btn-ghost" :disabled="aiTesting" @click="testAiConnection">
              {{ aiTestResult ? aiTestResult : (aiTesting ? '测试中...' : '测试连接') }}
            </button>
          </div>
        </div>

        <!-- 平台连接 -->
        <div class="card">
          <div class="card-header">🔗 {{ labels.settings.platformConnections.title }}</div>

          <div class="form-group platform-row">
            <div class="platform-info">
              <strong>{{ labels.settings.platformConnections.youtube.title }}</strong>
              <span class="badge" :class="youtubeConnected ? 'badge-success' : 'badge-warn'">
                {{ youtubeConnected ? labels.settings.platformConnections.youtube.connected : labels.settings.platformConnections.youtube.notConnected }}
              </span>
            </div>
            <div v-if="youtubeConnected" class="platform-detail">
              <span>{{ labels.settings.platformConnections.youtube.channel }}：<strong>{{ youtubeChannel }}</strong></span>
            </div>
            <div v-if="youtubeWaiting" class="form-hint" style="color: var(--accent)">
              {{ labels.settings.platformConnections.youtube.waitingAuth }}
            </div>
            <div class="btn-row" style="margin-top: 8px">
              <button
                v-if="!youtubeConnected"
                class="btn btn-primary btn-sm"
                :disabled="youtubeLoading"
                @click="connectYouTube"
              >{{ youtubeLoading ? labels.settings.platformConnections.youtube.connecting : labels.settings.platformConnections.youtube.connect }}</button>
              <button
                v-if="youtubeConnected"
                class="btn btn-ghost btn-sm"
                :disabled="youtubeLoading"
                @click="disconnectYouTube"
              >{{ youtubeLoading ? labels.settings.platformConnections.youtube.disconnecting : labels.settings.platformConnections.youtube.disconnect }}</button>
            </div>
          </div>

          <!-- Webhook 连接器配置 -->
          <div style="margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px">
            <div style="font-size: 13px; font-weight: 600; margin-bottom: 10px">{{ labels.settings.platformConnections.webhook.title }}</div>

            <div v-for="wh in webhookPlatforms" :key="wh.platform_id" class="form-group platform-row">
              <div class="platform-info">
                <strong>{{ wh.name }}</strong>
                <span class="badge" :class="wh.configured ? 'badge-success' : 'badge-warn'">
                  {{ wh.configured ? labels.settings.platformConnections.webhook.connected : labels.settings.platformConnections.webhook.notConnected }}
                </span>
                <span v-if="wh.configured" class="platform-detail" style="margin: 0">{{ wh.urlPreview }}</span>
              </div>

              <!-- Inline edit form -->
              <div v-if="webhookEditing === wh.platform_id" class="webhook-form">
                <div class="form-row" style="margin-bottom:6px">
                  <label style="width:80px; font-size:12px; color:var(--muted)">{{ labels.settings.platformConnections.webhook.url }}</label>
                  <input v-model="webhookForm.url" class="form-input" :placeholder="labels.settings.platformConnections.webhook.urlPlaceholder" />
                </div>
                <div class="form-row" style="margin-bottom:6px">
                  <label style="width:80px; font-size:12px; color:var(--muted)">{{ labels.settings.platformConnections.webhook.timeout }}</label>
                  <input v-model.number="webhookForm.timeout_s" type="number" class="form-input" style="width:80px" min="5" max="120" />
                </div>
                <div style="margin-bottom:6px">
                  <div style="font-size:11px; color:var(--muted); margin-bottom:4px">{{ labels.settings.platformConnections.webhook.headers }}</div>
                  <div v-for="(h, i) in webhookForm.headers" :key="i" class="form-row" style="margin-bottom:4px">
                    <input v-model="h.key" class="form-input" :placeholder="labels.settings.platformConnections.webhook.headerKey" style="width:120px" />
                    <input v-model="h.value" class="form-input" :placeholder="labels.settings.platformConnections.webhook.headerValue" />
                    <button class="btn btn-ghost btn-sm" @click="webhookForm.headers.splice(i, 1)" style="padding:2px 6px">✕</button>
                  </div>
                  <button class="btn btn-ghost btn-sm" @click="webhookForm.headers.push({ key: '', value: '' })" style="font-size:11px">+ {{ labels.settings.platformConnections.webhook.addHeader }}</button>
                </div>
                <div class="btn-row" style="margin-top:8px">
                  <button class="btn btn-primary btn-sm" :disabled="webhookSaving" @click="saveWebhook(wh.platform_id)">{{ webhookSaving ? labels.settings.platformConnections.webhook.saving : labels.settings.platformConnections.webhook.save }}</button>
                  <button class="btn btn-ghost btn-sm" @click="webhookEditing = null">{{ labels.settings.platformConnections.webhook.cancel }}</button>
                </div>
              </div>

              <!-- Action buttons -->
              <div v-else class="btn-row" style="margin-top: 6px">
                <button class="btn btn-ghost btn-sm" @click="startEditWebhook(wh)">
                  {{ wh.configured ? labels.settings.platformConnections.webhook.edit : labels.settings.platformConnections.webhook.configure }}
                </button>
                <button v-if="wh.configured" class="btn btn-ghost btn-sm" :disabled="webhookTesting" @click="testWebhook(wh.platform_id)">
                  {{ webhookTesting === wh.platform_id ? labels.settings.platformConnections.webhook.testing : labels.settings.platformConnections.webhook.test }}
                </button>
                <button v-if="wh.configured" class="btn btn-ghost btn-sm" style="color: #f87171" @click="deleteWebhook(wh.platform_id)">
                  {{ labels.settings.platformConnections.webhook.delete }}
                </button>
              </div>
              <div v-if="webhookTestResult && webhookTestResult.platform === wh.platform_id" class="form-hint" :style="{ color: webhookTestResult.ok ? 'var(--success)' : '#f87171' }">
                {{ webhookTestResult.message }}
              </div>
            </div>
          </div>
        </div>

        <!-- 界面设置 -->
        <div class="card">
          <div class="card-header">🎨 {{ labels.settings.ui.title }}</div>

          <div class="form-group">
            <label class="form-label">
              <input type="checkbox" v-model="appStore.uiSettings.creator_mode" />
              {{ labels.settings.ui.creatorMode }}
            </label>
            <div class="form-hint">{{ labels.settings.ui.creatorModeHint }}</div>
          </div>

          <div class="form-group">
            <label class="form-label">{{ labels.settings.ui.fontScale }}（{{ appStore.uiSettings.font_scale }}）</label>
            <input type="range" v-model.number="appStore.uiSettings.font_scale" min="0.85" max="1.45" step="0.05" style="width: 200px" />
          </div>

          <div class="form-group">
            <label class="form-label">{{ labels.settings.ui.defaultVideosDir }}</label>
            <div class="form-row">
              <input v-model="appStore.uiSettings.default_videos_dir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('uiSettings.default_videos_dir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">{{ labels.settings.ui.defaultProjectDir }}</label>
            <div class="form-row">
              <input v-model="appStore.uiSettings.default_project_dir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('uiSettings.default_project_dir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">
              <input type="checkbox" v-model="appStore.uiSettings.auto_open_last_project" />
              {{ labels.settings.ui.autoOpenLast }}
            </label>
          </div>

          <button class="btn btn-primary" :disabled="appStore.uiSettingsSaving" @click="appStore.saveUiSettings()">
            {{ appStore.uiSettingsSaving ? labels.common.loading : labels.settings.ui.save }}
          </button>

          <span v-if="appStore.uiSettingsMessage" style="margin-left: 12px; font-size: 13px; color: var(--success)">
            {{ appStore.uiSettingsMessage }}
          </span>
        </div>

        <!-- 并发设置 -->
        <div class="card">
          <div class="card-header">⚡ 并发任务</div>
          <div class="form-group">
            <label class="form-label">同时渲染任务数（{{ queueMaxRunning }}）</label>
            <input type="range" v-model.number="queueMaxRunning" min="1" max="3" step="1" style="width: 200px" />
            <div class="form-hint">建议 1-2，更高会占用更多 CPU 和内存</div>
          </div>
          <button class="btn btn-primary btn-sm" :disabled="queueLoading" @click="saveQueueConfig()">
            {{ queueLoading ? '保存中…' : '保存' }}
          </button>
        </div>

        <!-- 系统自检 -->
        <div class="card">
          <div class="card-header">🔧 系统自检</div>

          <div v-if="appStore.preflightReport?.checks" class="preflight-list">
            <div v-for="check in appStore.preflightReport.checks" :key="check.id || check.name" class="preflight-item">
              <span class="badge" :class="badgeClass(check.status)">
                {{ statusText(check.status) }}
              </span>
              <span>{{ check.title || check.label || check.id || check.name }}</span>
              <span v-if="check.detail || check.message" class="text-muted" style="font-size: 12px">{{ check.detail || check.message }}</span>
            </div>
          </div>

          <p v-if="appStore.preflightMessage" style="font-size: 13px; color: var(--muted); margin-top: 8px">
            {{ appStore.preflightMessage }}
          </p>

          <button class="btn btn-ghost" style="margin-top: 12px" :disabled="appStore.preflightLoading" @click="appStore.runSystemPreflight(true)">
            {{ appStore.preflightLoading ? '检查中…' : '重新检查' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useApiStore } from '../stores/api.js'
import { useSettingsStore } from '../stores/settings.js'
import { useValidation } from '../composables/useValidation.js'
import labels from '../i18n/labels.js'
import AppNav from '../components/layout/AppNav.vue'
import ProjectTitle from '../components/common/ProjectTitle.vue'
import FormField from '../components/common/FormField.vue'

const appStore = useAppStore()
const apiStore = useApiStore()
const settings = useSettingsStore()

const v = useValidation({
  ai_base_url: [{ type: 'url', message: '请输入合法的 URL 地址' }],
})

// ── YouTube OAuth ──
const youtubeConnected = ref(false)
const youtubeChannel = ref('')
const youtubeLoading = ref(false)
const youtubeWaiting = ref(false)
let ytPollTimer = null

const aiTesting = ref(false)
const aiTestResult = ref('')

async function testAiConnection() {
  aiTesting.value = true
  aiTestResult.value = ''
  const data = await apiStore.api('POST', '/api/settings/ai/test', {})
  aiTesting.value = false
  if (data.ok) {
    aiTestResult.value = '✓ 连接成功'
  } else {
    aiTestResult.value = `连接失败：${data.error || '未知错误'}`
  }
  setTimeout(() => { aiTestResult.value = '' }, 5000)
}

async function loadYouTubeStatus() {
  const data = await apiStore.api('GET', '/api/settings/oauth/youtube/status')
  if (data && data.connected) {
    youtubeConnected.value = true
    youtubeChannel.value = data.channel_name || ''
    youtubeWaiting.value = false
  } else {
    youtubeConnected.value = false
    youtubeChannel.value = ''
  }
}

async function connectYouTube() {
  youtubeLoading.value = true
  const data = await apiStore.api('POST', '/api/settings/oauth/youtube/start', {})
  youtubeLoading.value = false
  if (data && data.error) {
    appStore.showToast?.(data.error, 'danger')
    return
  }
  // Start polling for connection
  youtubeWaiting.value = true
  ytPollTimer = setInterval(async () => {
    const status = await apiStore.api('GET', '/api/settings/oauth/youtube/status')
    if (status && status.connected) {
      youtubeConnected.value = true
      youtubeChannel.value = status.channel_name || ''
      youtubeWaiting.value = false
      clearInterval(ytPollTimer)
      ytPollTimer = null
    }
  }, 3000)
  // Stop polling after 5 minutes
  setTimeout(() => {
    if (ytPollTimer) { clearInterval(ytPollTimer); ytPollTimer = null; youtubeWaiting.value = false }
  }, 300000)
}

async function disconnectYouTube() {
  if (!confirm(labels.settings.platformConnections.youtube.disconnectConfirm)) return
  youtubeLoading.value = true
  await apiStore.api('POST', '/api/settings/oauth/youtube/disconnect', {})
  youtubeLoading.value = false
  youtubeConnected.value = false
  youtubeChannel.value = ''
}

// ── Webhook 连接器 ──
const webhookPlatforms = ref([])
const webhookEditing = ref(null)
const webhookForm = reactive({ url: '', timeout_s: 30, headers: [] })
const webhookSaving = ref(false)
const webhookTesting = ref(null)
const webhookTestResult = ref(null)

// Non-OAuth platforms that use webhook connectors
const WEBHOOK_PLATFORM_IDS = ['douyin', 'xiaohongshu', 'wechat_channels', 'wechat_mp', 'ixigua', 'instagram', 'twitter']

async function loadWebhookConnectors() {
  const data = await apiStore.api('GET', '/api/settings/connectors')
  if (!data || data.error) return
  const connectors = data.connectors || {}
  webhookPlatforms.value = WEBHOOK_PLATFORM_IDS.map(pid => {
    const c = connectors[pid]
    const configured = !!(c && (c.endpoint || c.url))
    const rawUrl = c?.endpoint || c?.url || ''
    return {
      platform_id: pid,
      name: platformDisplayName(pid),
      configured,
      urlPreview: configured ? rawUrl.slice(0, 25) + (rawUrl.length > 25 ? '…' : '') : '',
      connector: c || null,
    }
  })
}

function platformDisplayName(pid) {
  const map = {
    douyin: '抖音', xiaohongshu: '小红书', wechat_channels: '微信视频号',
    wechat_mp: '微信公众号', ixigua: '西瓜视频', instagram: 'Instagram', twitter: 'Twitter/X',
  }
  return map[pid] || pid
}

function startEditWebhook(wh) {
  webhookEditing.value = wh.platform_id
  webhookTestResult.value = null
  if (wh.configured && wh.connector) {
    webhookForm.url = wh.connector.endpoint || wh.connector.url || ''
    webhookForm.timeout_s = wh.connector.timeout_s || 30
    const hdr = wh.connector.headers || {}
    webhookForm.headers = Object.entries(hdr).map(([key, value]) => ({ key, value: String(value) }))
  } else {
    webhookForm.url = ''
    webhookForm.timeout_s = 30
    webhookForm.headers = []
  }
}

async function saveWebhook(platformId) {
  webhookSaving.value = true
  const headers = {}
  for (const h of webhookForm.headers) {
    if (h.key.trim()) headers[h.key.trim()] = h.value
  }
  await apiStore.api('PUT', `/api/settings/connectors/${platformId}`, {
    url: webhookForm.url,
    headers,
    timeout_s: webhookForm.timeout_s,
  })
  webhookSaving.value = false
  webhookEditing.value = null
  loadWebhookConnectors()
}

async function deleteWebhook(platformId) {
  if (!confirm(labels.settings.platformConnections.webhook.deleteConfirm)) return
  await apiStore.api('DELETE', `/api/settings/connectors/${platformId}`)
  loadWebhookConnectors()
}

async function testWebhook(platformId) {
  webhookTesting.value = platformId
  webhookTestResult.value = null
  const data = await apiStore.api('POST', `/api/settings/connectors/${platformId}/test`)
  webhookTesting.value = null
  if (data && !data.error) {
    webhookTestResult.value = {
      platform: platformId, ok: true,
      message: `${labels.settings.platformConnections.webhook.testSuccess}（${data.latency_ms}ms）`,
    }
  } else {
    webhookTestResult.value = {
      platform: platformId, ok: false,
      message: `${labels.settings.platformConnections.webhook.testFailed}：${data?.error || '未知错误'}`,
    }
  }
}

// 并发任务数
const queueMaxRunning = ref(2)
const queueLoading = ref(false)

async function loadQueueConfig() {
  const data = await apiStore.api('GET', '/api/system/queue-config')
  if (data && data.max_running) queueMaxRunning.value = data.max_running
}

async function saveQueueConfig() {
  queueLoading.value = true
  await apiStore.api('POST', '/api/system/queue-config', { max_running: queueMaxRunning.value })
  queueLoading.value = false
}

function badgeClass(status) {
  const key = `${status || ''}`.trim().toLowerCase()
  if (key === 'ok') return 'badge-success'
  if (key === 'error') return 'badge-danger'
  return 'badge-warn'
}

function statusText(status) {
  const key = `${status || ''}`.trim().toLowerCase()
  if (key === 'ok') return '通过'
  if (key === 'error') return '阻塞'
  if (key === 'warning') return '需关注'
  return key || '未知'
}

function fillUrl() {
  const recommended = settings.recommendedBaseUrl(settings.aiSettings.provider, settings.aiSettings.ai_model)
  if (recommended) {
    settings.aiSettings.ai_base_url = recommended
    settings.aiMessage = `已填充推荐地址：${recommended}`
  } else {
    settings.aiMessage = '当前服务商没有预设推荐地址，可手动填写。'
  }
}

onMounted(async () => {
  await settings.loadAiSettings()
  loadQueueConfig()
  loadYouTubeStatus()
  loadWebhookConnectors()
})
</script>

<style scoped>
.preflight-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preflight-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.platform-row { margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.platform-row:last-child { border-bottom: none; }
.platform-info { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.platform-detail { font-size: 13px; color: var(--muted); margin-bottom: 4px; }
.btn-row { display: flex; gap: 8px; }
.webhook-form { margin-top: 8px; padding: 10px; background: var(--surface2); border-radius: 8px; }
.webhook-form .form-row { display: flex; align-items: center; gap: 8px; }
</style>
