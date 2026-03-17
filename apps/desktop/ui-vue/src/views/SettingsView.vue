<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <span class="project-path" :title="appStore.projectDir">{{ projectDisplayName }}</span>
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
            <label class="form-label">OpenAI API Key</label>
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
          </div>

          <div class="form-group">
            <label class="form-label">Anthropic API Key</label>
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
          </div>

          <div v-if="settings.aiMessage" class="badge badge-info" style="margin-bottom: 12px">
            {{ settings.aiMessage }}
          </div>

          <button class="btn btn-primary" :disabled="settings.aiSaving" @click="settings.saveAiSettings()">
            {{ settings.aiSaving ? labels.settings.ai.saving : labels.settings.ai.save }}
          </button>
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
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useApiStore } from '../stores/api.js'
import { useSettingsStore } from '../stores/settings.js'
import { useValidation } from '../composables/useValidation.js'
import labels from '../i18n/labels.js'
import AppNav from '../components/layout/AppNav.vue'
import FormField from '../components/common/FormField.vue'

const appStore = useAppStore()
const apiStore = useApiStore()
const settings = useSettingsStore()

const projectDisplayName = computed(() => {
  const dir = appStore.projectDir
  if (!dir) return '未打开项目'
  const name = dir.split('/').filter(Boolean).pop() || dir
  const m = name.match(/^proj_selected_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/)
  if (m) return `项目 ${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`
  return name
})

const v = useValidation({
  ai_base_url: [{ type: 'url', message: '请输入合法的 URL 地址' }],
})

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
  await loadQueueConfig()
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
</style>
