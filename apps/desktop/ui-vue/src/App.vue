<template>
  <div id="app-root">
    <!-- 中断任务恢复横幅 -->
    <div v-if="system.interruptedBannerVisible" class="interrupted-banner">
      <span class="interrupted-banner-text">
        {{ L.interruptedJobs.banner.replace('{count}', system.interruptedJobs.length) }}
      </span>
      <button class="interrupted-banner-btn" @click="showPanel = true">
        {{ L.interruptedJobs.bannerAction }}
      </button>
      <button class="interrupted-banner-close" @click="system.dismissInterruptedBanner()">✕</button>
    </div>

    <!-- 中断任务恢复面板（浮层） -->
    <div v-if="showPanel" class="interrupted-overlay" @click.self="showPanel = false">
      <div class="interrupted-modal">
        <InterruptedJobsPanel />
        <button class="interrupted-modal-close" @click="showPanel = false">{{ L.common.close }}</button>
      </div>
    </div>

    <router-view />
    <ToastContainer />
    <OnboardingModal v-if="appStore.showOnboardingWizard" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { labels as L } from './i18n/labels.js'
import { useAppStore } from './stores/app.js'
import { useSystemStore } from './stores/system.js'
import ToastContainer from './components/common/ToastContainer.vue'
import OnboardingModal from './components/onboarding/OnboardingModal.vue'
import InterruptedJobsPanel from './components/common/InterruptedJobsPanel.vue'

const appStore = useAppStore()
const system = useSystemStore()
const showPanel = ref(false)

onMounted(async () => {
  // 延迟检查中断任务，等应用初始化完成
  setTimeout(() => {
    system.loadInterruptedJobs()
  }, 2000)
})
</script>

<style scoped>
.interrupted-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9000;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: rgba(240, 173, 78, 0.95);
  color: #1a1a1a;
  font-size: 13px;
  font-weight: 500;
  backdrop-filter: blur(8px);
}

.interrupted-banner-text {
  flex: 1;
}

.interrupted-banner-btn {
  background: rgba(0, 0, 0, 0.15);
  border: none;
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #1a1a1a;
  cursor: pointer;
}

.interrupted-banner-btn:hover {
  background: rgba(0, 0, 0, 0.25);
}

.interrupted-banner-close {
  background: none;
  border: none;
  color: #1a1a1a;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  opacity: 0.6;
}

.interrupted-banner-close:hover {
  opacity: 1;
}

.interrupted-overlay {
  position: fixed;
  inset: 0;
  z-index: 9500;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.interrupted-modal {
  background: var(--bg-primary, #1e1e1e);
  border-radius: 12px;
  padding: 20px;
  max-width: 520px;
  width: 90%;
  max-height: 70vh;
  overflow-y: auto;
}

.interrupted-modal-close {
  display: block;
  margin: 12px auto 0;
  background: transparent;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
  border-radius: 6px;
  padding: 6px 20px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
}
</style>
