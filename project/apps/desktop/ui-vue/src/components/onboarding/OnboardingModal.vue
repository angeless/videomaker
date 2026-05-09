<template>
  <Teleport to="body">
    <div class="modal-overlay">
      <div class="modal" style="min-width: 480px">
        <div class="modal-title">{{ L.onboarding.title }}</div>

        <!-- 步骤指示 (v0.19 M3: 4 step now — welcome / ai-key / ingest / create) -->
        <div class="onboarding-steps">
          <div
            v-for="i in 4"
            :key="i"
            class="onboarding-dot"
            :class="{ active: step === i - 1, done: step > i - 1 }"
          ></div>
        </div>

        <!-- Step 0: 欢迎 -->
        <div v-if="step === 0" class="onboarding-content">
          <h3>{{ L.onboarding.step1Title }}</h3>
          <p>{{ L.onboarding.step1Desc }}</p>
          <div class="feature-list">
            <div v-for="f in L.onboarding.step1Features" :key="f" class="feature-item">
              <span class="feature-icon">✦</span> {{ f }}
            </div>
          </div>
        </div>

        <!-- Step 1: 配置 AI 标签 (v0.19 M3 — 可选；跳过则用颜色规则) -->
        <div v-if="step === 1" class="onboarding-content">
          <h3>配置 AI 标签 <span class="onboarding-optional">（可选）</span></h3>
          <p>
            配置 OpenAI 或 Anthropic API Key 后，素材标签由 AI 视觉模型生成，
            准确度比颜色规则推断**显著提升**。未配置不影响其它功能（指纹去重、转录等）。
          </p>
          <div class="ai-key-cta">
            <div class="ai-key-status" :class="aiKeyStatusClass">
              <span class="ai-key-icon">{{ aiKeyConfigured ? '✓' : '○' }}</span>
              <span>{{ aiKeyConfigured ? `已配置 ${aiKeyProvider}` : '尚未配置任何 Provider' }}</span>
            </div>
            <button class="btn btn-primary" @click="goToSettingsAi">
              {{ aiKeyConfigured ? '修改配置' : '去 Settings 配置' }}
            </button>
          </div>
          <div class="ai-key-hint">
            提示：配置完成后回到此页可点"下一步"继续；不配置请点"稍后再说"。
          </div>
        </div>

        <!-- Step 2: 导入素材 -->
        <div v-if="step === 2" class="onboarding-content">
          <h3>{{ L.onboarding.step2Title }}</h3>
          <p>{{ L.onboarding.step2Desc }}</p>

          <div v-if="!selectedFolder" class="onboarding-action-area">
            <button class="btn btn-primary" @click="pickFolder">
              {{ L.onboarding.step2SelectFolder }}
            </button>
          </div>

          <div v-else class="onboarding-action-area">
            <div class="folder-info">
              <span class="folder-label">{{ L.onboarding.step2FolderSelected }}</span>
              <span class="folder-path" :title="selectedFolder">{{ shortenPath(selectedFolder) }}</span>
            </div>
            <div class="folder-actions">
              <button class="btn btn-ghost btn-sm" @click="pickFolder">{{ L.onboarding.step2SelectFolder }}</button>
              <button
                v-if="!ingestStarted"
                class="btn btn-primary"
                @click="startIngest"
              >{{ L.onboarding.step2StartIngest }}</button>
              <span v-else-if="ingestDone" class="ingest-status success">{{ L.onboarding.step2IngestDone }}</span>
              <span v-else class="ingest-status working">{{ L.onboarding.step2Ingesting }}</span>
            </div>
          </div>
        </div>

        <!-- Step 3: 开始创作 (was step 2 before M3) -->
        <div v-if="step === 3" class="onboarding-content">
          <h3>{{ L.onboarding.step3Title }}</h3>
          <p>{{ L.onboarding.step3Desc }}</p>
          <div class="onboarding-action-area finish-actions">
            <button class="btn btn-primary" @click="goLibrary">{{ L.onboarding.step3GoLibrary }}</button>
            <button class="btn btn-success" @click="goCreate">{{ L.onboarding.step3GoCreate }}</button>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="skip">
            {{ L.onboarding.skip }}
          </button>
          <div style="flex: 1"></div>
          <button v-if="step > 0" class="btn btn-ghost" @click="prevStep">
            {{ L.onboarding.prev }}
          </button>
          <button v-if="step === 0" class="btn btn-primary" @click="nextStep">
            {{ L.onboarding.start }}
          </button>
          <button v-else-if="step === 1" class="btn btn-primary" @click="nextStep">
            {{ aiKeyConfigured ? '下一步' : '稍后再说' }}
          </button>
          <button v-else-if="step === 2" class="btn btn-primary" @click="nextStep" :disabled="!canAdvanceFromStep1">
            {{ L.onboarding.next }}
          </button>
          <button v-else class="btn btn-success" @click="finish">
            {{ L.onboarding.finish }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAppStore } from '../../stores/app.js'
import { usePreferencesStore } from '../../stores/preferences.js'
import { useApiStore } from '../../stores/api.js'
import labels from '../../i18n/labels.js'

const L = labels
const appStore = useAppStore()
const prefs = usePreferencesStore()
const apiStore = useApiStore()

// v0.19 M3: 4 steps now (welcome / ai-key / ingest / create)
// Resume from persisted step (but never beyond step 3)
const step = ref(Math.min(prefs.uiSettings.onboarding_step || 0, 3))

const selectedFolder = ref('')
const ingestStarted = ref(false)
const ingestDone = ref(false)
const ingestJobId = ref('')

// v0.19 M3: AI key configuration state — refreshed on step entry & after Settings return
const aiKeyConfigured = ref(false)
const aiKeyProvider = ref('')

const aiKeyStatusClass = computed(() =>
  aiKeyConfigured.value ? 'ai-key-status-ready' : 'ai-key-status-pending'
)

async function refreshAiKeyStatus() {
  try {
    const data = await apiStore.api('GET', '/api/library/llm-status')
    aiKeyConfigured.value = !!data?.enabled
    if (data?.providers?.openai) aiKeyProvider.value = 'OpenAI'
    else if (data?.providers?.anthropic) aiKeyProvider.value = 'Anthropic'
    else aiKeyProvider.value = ''
  } catch {
    // Endpoint failure → treat as not configured (banner / step still works)
    aiKeyConfigured.value = false
    aiKeyProvider.value = ''
  }
}

function goToSettingsAi() {
  // Dismiss the modal so user can configure; banner in Library will reappear
  // until they configure (M2). M9 anchor gets us straight to AI card.
  appStore.dismissOnboarding(true)
  window.location.hash = '#/settings'
  // Hash change to anchor needs a tick — use setTimeout to scroll after route mount
  setTimeout(() => {
    const el = document.getElementById('ai-config')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, 200)
}

const canAdvanceFromStep1 = computed(() => {
  // User can advance if they selected a folder (ingest is optional)
  return !!selectedFolder.value
})

function persistStep(s) {
  prefs.uiSettings.onboarding_step = s
  prefs.saveUiSettings()
}

function nextStep() {
  if (step.value < 3) {
    step.value++
    persistStep(step.value)
    if (step.value === 1) refreshAiKeyStatus()
  }
}

function prevStep() {
  if (step.value > 0) {
    step.value--
    persistStep(step.value)
  }
}

function onEscKey(e) {
  if (e.key === 'Escape') skip()
}
onMounted(() => {
  window.addEventListener('keydown', onEscKey)
  // v0.19 M3: refresh AI key status if user resumed onboarding at step 1
  if (step.value === 1) refreshAiKeyStatus()
})
onUnmounted(() => {
  window.removeEventListener('keydown', onEscKey)
  // Stop the ingest job poll chain (Round-14).
  _pollAlive = false
  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null }
})

function skip() {
  appStore.dismissOnboarding(true)
}

function finish() {
  appStore.dismissOnboarding(true)
}

function goLibrary() {
  appStore.dismissOnboarding(true)
  window.location.hash = '#/library'
}

function goCreate() {
  appStore.dismissOnboarding(true)
  window.location.hash = '#/create/guide'
}

async function pickFolder() {
  const data = await apiStore.api('POST', '/api/dialog/folder')
  if (data.path) {
    selectedFolder.value = data.path
    ingestStarted.value = false
    ingestDone.value = false
  }
}

async function startIngest() {
  if (!selectedFolder.value || ingestStarted.value) return
  ingestStarted.value = true
  const data = await apiStore.api('POST', '/api/library/ingest/local', {
    path: selectedFolder.value,
  })
  if (data.ok && data.job_id) {
    ingestJobId.value = data.job_id
    pollIngestJob()
  } else {
    ingestDone.value = true
  }
}

// Round-14: track the poll timer so onBeforeUnmount can stop the chain.
// Previously the recursive setTimeout kept hitting /api/jobs/{id} after the
// modal was dismissed, wasting network traffic + logging noise.
let _pollTimer = null
let _pollAlive = true

async function pollIngestJob() {
  if (!ingestJobId.value) { ingestDone.value = true; return }
  const check = async () => {
    if (!_pollAlive) return
    const data = await apiStore.api('GET', `/api/jobs/${ingestJobId.value}`)
    if (!_pollAlive) return
    if (!data || data.status === 'done' || data.status === 'error') {
      ingestDone.value = true
      return
    }
    _pollTimer = setTimeout(check, 2000)
  }
  _pollTimer = setTimeout(check, 2000)
}

function shortenPath(p) {
  if (!p) return ''
  const parts = p.split('/')
  if (parts.length <= 3) return p
  return '.../' + parts.slice(-2).join('/')
}
</script>

<style scoped>
.onboarding-steps {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
}

.onboarding-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--border);
  transition: background 0.2s;
}

.onboarding-dot.active {
  background: var(--accent);
}

.onboarding-dot.done {
  background: var(--success);
}

.onboarding-content {
  min-height: 120px;
}

.onboarding-content h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.onboarding-content p {
  font-size: 14px;
  color: var(--muted);
  line-height: 1.7;
  margin-bottom: 12px;
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.feature-item {
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* v0.19 M3: AI Key configuration step styles */
.onboarding-optional {
  font-size: 13px;
  font-weight: 400;
  color: var(--text-muted, #888);
  margin-left: 6px;
}

.ai-key-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  margin-top: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
  border-radius: 8px;
}

.ai-key-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.ai-key-status-ready { color: #10b981; }
.ai-key-status-pending { color: var(--text-muted, #888); }

.ai-key-icon {
  font-size: 16px;
  font-weight: 700;
}

.ai-key-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-muted, #888);
  line-height: 1.5;
}

.feature-icon {
  color: var(--accent);
  font-size: 13px;
}

.onboarding-action-area {
  margin-top: 12px;
}

.folder-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 10px;
  background: var(--surface2);
  border-radius: 6px;
}

.folder-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.folder-path {
  font-size: 12px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ingest-status {
  font-size: 13px;
  padding: 4px 10px;
  border-radius: 4px;
}

.ingest-status.working {
  color: var(--accent);
}

.ingest-status.success {
  color: var(--success);
}

.finish-actions {
  display: flex;
  gap: 10px;
}
</style>
