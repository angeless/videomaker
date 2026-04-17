<template>
  <Teleport to="body">
    <div class="modal-overlay">
      <div class="modal" style="min-width: 480px">
        <div class="modal-title">{{ L.onboarding.title }}</div>

        <!-- 步骤指示 -->
        <div class="onboarding-steps">
          <div
            v-for="i in 3"
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

        <!-- Step 1: 导入素材 -->
        <div v-if="step === 1" class="onboarding-content">
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

        <!-- Step 2: 开始创作 -->
        <div v-if="step === 2" class="onboarding-content">
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
          <button v-else-if="step === 1" class="btn btn-primary" @click="nextStep" :disabled="!canAdvanceFromStep1">
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

// Resume from persisted step (but never beyond step 2)
const step = ref(Math.min(prefs.uiSettings.onboarding_step || 0, 2))

const selectedFolder = ref('')
const ingestStarted = ref(false)
const ingestDone = ref(false)
const ingestJobId = ref('')

const canAdvanceFromStep1 = computed(() => {
  // User can advance if they selected a folder (ingest is optional)
  return !!selectedFolder.value
})

function persistStep(s) {
  prefs.uiSettings.onboarding_step = s
  prefs.saveUiSettings()
}

function nextStep() {
  if (step.value < 2) {
    step.value++
    persistStep(step.value)
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
onMounted(() => window.addEventListener('keydown', onEscKey))
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
  window.location.hash = '#/create/workflow'
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
