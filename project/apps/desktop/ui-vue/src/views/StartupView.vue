<template>
  <div class="startup-view">
    <div class="startup-card">
      <h1 class="startup-title">{{ labels.appTitle }}</h1>

      <div class="startup-progress">
        <div class="progress-bar">
          <div class="progress-bar-fill" :class="{ success: done }" :style="{ width: progressPct + '%' }"></div>
        </div>
        <p class="startup-status">{{ statusText }}</p>
      </div>

      <!-- 自检失败详情 -->
      <div v-if="showDetails" class="startup-details">
        <div v-if="appStore.preflightReport?.checks" class="preflight-checks">
          <div
            v-for="check in appStore.preflightReport.checks"
            :key="check.name"
            class="preflight-check"
          >
            <span class="badge" :class="preflightBadgeClass(check.status)">
              {{ preflightStatusText(check.status) }}
            </span>
            <span>{{ check.label || check.name }}</span>
          </div>
        </div>
        <p v-if="appStore.preflightMessage" class="text-danger" style="margin-top: 12px">
          {{ appStore.preflightMessage }}
        </p>
        <div class="startup-actions" style="margin-top: 16px; display: flex; gap: 8px">
          <button class="btn btn-primary" @click="retry">
            返回检查
          </button>
          <button class="btn btn-ghost" @click="acknowledgeAndContinue">
            了解风险，继续进入
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app.js'
import { useSettingsStore } from '../stores/settings.js'
import labels from '../i18n/labels.js'

const router = useRouter()
const appStore = useAppStore()
const settingsStore = useSettingsStore()

const progressPct = ref(0)
const statusText = ref(labels.startup.checking)
const done = ref(false)
const showDetails = ref(false)

function preflightBadgeClass(status) {
  const key = `${status || ''}`.trim().toLowerCase()
  if (key === 'ok') return 'badge-success'
  if (key === 'error') return 'badge-danger'
  return 'badge-warn'
}

function preflightStatusText(status) {
  const key = `${status || ''}`.trim().toLowerCase()
  if (key === 'ok') return '通过'
  if (key === 'error') return '阻塞'
  if (key === 'warning') return '需关注'
  return key || '未知'
}

async function runStartup() {
  progressPct.value = 10
  statusText.value = labels.startup.checking

  // 1) Bootstrap API session
  const { useApiStore } = await import('../stores/api.js')
  const apiStore = useApiStore()
  await apiStore.bootstrap()
  progressPct.value = 25

  // 2) Load UI settings
  statusText.value = labels.startup.loadingSettings
  await appStore.loadUiSettings()
  progressPct.value = 40

  // 3) Run preflight
  statusText.value = labels.startup.checking
  const ok = await appStore.runSystemPreflight(false)
  progressPct.value = 60

  // 4) Load AI settings
  await settingsStore.loadAiSettings()
  progressPct.value = 75

  // 5) Fetch status
  await appStore.fetchStatus()
  progressPct.value = 90

  // 6) Refresh task queue
  await appStore.refreshTaskQueue()
  progressPct.value = 100

  appStore.loading = false
  done.value = true

  if (!ok) {
    statusText.value = labels.startup.failed
    showDetails.value = true
    return
  }

  statusText.value = labels.startup.ready

  // Auto-navigate after brief pause
  await new Promise(r => setTimeout(r, 400))

  if (appStore.hasProject) {
    router.replace('/create/workflow')
  } else {
    router.replace('/library')
  }
}

async function retry() {
  showDetails.value = false
  done.value = false
  await runStartup()
}

function acknowledgeAndContinue() {
  appStore.preflightAcknowledged = true
  if (appStore.hasProject) {
    router.replace('/create/workflow')
  } else {
    router.replace('/library')
  }
}

onMounted(() => {
  runStartup()
})
</script>

<style scoped>
.startup-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: var(--bg);
}

.startup-card {
  text-align: center;
  max-width: 420px;
  width: 100%;
  padding: 48px 32px;
}

.startup-title {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 32px;
  color: var(--text);
}

.startup-progress {
  margin-bottom: 24px;
}

.startup-status {
  font-size: 13px;
  color: var(--muted);
  margin-top: 12px;
}

.startup-details {
  text-align: left;
  margin-top: 24px;
}

.preflight-checks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preflight-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
</style>
