<template>
  <div class="roughcut-view">
    <!-- Top bar -->
    <div class="rc-topbar">
      <h2 class="rc-title">智能粗剪</h2>
      <div class="rc-meta" v-if="store.sessionId">
        <span class="rc-badge" :class="store.videoType">{{ videoTypeLabel }}</span>
        <span class="text-muted">语音占比 {{ (store.speechRatio * 100).toFixed(0) }}%</span>
        <span class="text-muted">v{{ store.currentVersion }}</span>
      </div>
      <div class="rc-topbar-actions">
        <button
          v-if="store.sessionId && store.videoType !== 'scenic'"
          class="btn btn-ghost btn-sm"
          @click="loadTranscript"
          :disabled="store.status === 'loading'"
        >
          加载转录
        </button>
        <button
          v-if="store.sessionId"
          class="btn btn-ghost btn-sm"
          @click="loadScenes"
          :disabled="store.status === 'loading'"
        >
          场景分割
        </button>
        <button
          v-if="store.sessionId"
          class="btn btn-primary btn-sm"
          @click="generate"
          :disabled="store.status === 'rendering'"
        >
          {{ store.status === 'rendering' ? '渲染中...' : '生成粗剪' }}
        </button>
      </div>
    </div>

    <!-- Init panel (no session) -->
    <div v-if="!store.sessionId" class="rc-init">
      <div class="rc-init-card">
        <p>选择一个视频文件开始智能粗剪</p>
        <div class="rc-init-form">
          <input
            type="text"
            v-model="initVideoPath"
            placeholder="视频文件路径"
            class="input"
          />
          <button class="btn btn-primary" @click="initSession" :disabled="!initVideoPath">
            开始分析
          </button>
        </div>
      </div>
    </div>

    <!-- Main workspace -->
    <div v-else class="rc-workspace">
      <!-- Left: Transcript editor (speech/mixed) -->
      <div
        v-if="store.videoType !== 'scenic'"
        class="rc-panel rc-transcript-panel"
      >
        <TranscriptEditor />
      </div>

      <!-- Right: Scene selector (scenic/mixed) -->
      <div
        v-if="store.videoType !== 'speech'"
        class="rc-panel rc-scene-panel"
      >
        <SceneSelector />
      </div>

      <!-- Full width for pure speech or pure scenic -->
      <div
        v-if="store.videoType === 'speech' || store.videoType === 'scenic'"
        class="rc-panel-full"
      >
        <TranscriptEditor v-if="store.videoType === 'speech'" />
        <SceneSelector v-if="store.videoType === 'scenic'" />
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="store.errorMessage" class="rc-error">
      {{ store.errorMessage }}
      <button class="btn btn-ghost btn-xs" @click="store.errorMessage = ''">关闭</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { computed } from 'vue'
import { useRoughcutStore } from '../stores/roughcut.js'
import TranscriptEditor from '../components/roughcut/TranscriptEditor.vue'
import SceneSelector from '../components/roughcut/SceneSelector.vue'

const store = useRoughcutStore()
const initVideoPath = ref('')

const videoTypeLabel = computed(() => {
  const map = { speech: '语音型', scenic: '风景型', mixed: '混合型' }
  return map[store.videoType] || store.videoType
})

async function initSession() {
  await store.initSession('.', initVideoPath.value)
}

async function loadTranscript() {
  await store.loadTranscript()
  await store.loadFillers()
}

async function loadScenes() {
  await store.loadScenes()
}

async function generate() {
  await store.generateRoughCut()
}
</script>

<style scoped>
.roughcut-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0;
}
.rc-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
  flex-shrink: 0;
}
.rc-title { font-size: 16px; font-weight: 700; margin: 0; }
.rc-meta { display: flex; gap: 8px; align-items: center; font-size: 12px; }
.rc-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.rc-badge.speech { background: rgba(59,130,246,0.2); color: #93c5fd; }
.rc-badge.scenic { background: rgba(16,185,129,0.2); color: #6ee7b7; }
.rc-badge.mixed { background: rgba(245,158,11,0.2); color: #fcd34d; }
.rc-topbar-actions { margin-left: auto; display: flex; gap: 6px; }

.rc-init {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rc-init-card {
  text-align: center;
  padding: 40px;
}
.rc-init-form {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}
.rc-init-form .input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-input, rgba(255,255,255,0.06));
  border: 1px solid var(--border, rgba(255,255,255,0.12));
  border-radius: 6px;
  color: inherit;
  font-size: 14px;
  min-width: 300px;
}

.rc-workspace {
  flex: 1;
  display: flex;
  gap: 1px;
  overflow: hidden;
}
.rc-panel {
  flex: 1;
  overflow: hidden;
}
.rc-panel-full {
  flex: 1;
  overflow: hidden;
}
.rc-transcript-panel { min-width: 0; }
.rc-scene-panel { min-width: 0; max-width: 400px; }

.rc-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(239,68,68,0.15);
  color: #fca5a5;
  font-size: 13px;
}
</style>
