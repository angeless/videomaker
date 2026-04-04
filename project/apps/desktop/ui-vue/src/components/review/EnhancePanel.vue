<script setup>
/**
 * EnhancePanel.vue — R13: Enhancement options panel.
 * Audio enhancement, TTS, BGM, transitions, reframe controls.
 */
import { ref, computed } from 'vue'
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()

const activeTab = ref('audio')

const tabs = [
  { key: 'audio', label: '音频增强' },
  { key: 'tts', label: 'TTS 配音' },
  { key: 'bgm', label: 'BGM' },
  { key: 'transition', label: '转场' },
  { key: 'reframe', label: '多平台裁剪' },
]

// Audio config
const audioDenoise = ref(true)
const audioEqualizer = ref(true)
const audioCompressor = ref(true)
const audioLoudnorm = ref(true)

// TTS config
const ttsVoice = ref('zh-female')
const ttsVoices = [
  { value: 'zh-female', label: '晓晓 (女声)' },
  { value: 'zh-male', label: '云希 (男声)' },
  { value: 'en-female', label: 'Jenny (EN-F)' },
  { value: 'en-male', label: 'Guy (EN-M)' },
]

// BGM config
const bgmVolume = ref(-12)
const bgmBeatSync = ref(false)

// Transition config
const transEffect = ref('cross_dissolve')
const transEffects = [
  'cut', 'fade_black', 'fade_white', 'cross_dissolve',
  'wipe_left', 'wipe_right', 'zoom_in', 'zoom_out',
  'black_title', 'whoosh', 'glitch', 'flash',
]

// Reframe config
const reframePlatform = ref('tiktok')
const platforms = [
  { value: 'tiktok', label: '抖音 9:16' },
  { value: 'instagram', label: 'Instagram 9:16' },
  { value: 'youtube', label: 'YouTube 16:9' },
  { value: 'shorts', label: 'Shorts 9:16' },
  { value: 'wechat', label: '微信 9:16' },
  { value: 'xiaohongshu', label: '小红书 3:4' },
  { value: 'square', label: '正方形 1:1' },
]

const enhancing = ref(false)

async function applyEnhance() {
  enhancing.value = true
  try {
    const sessionId = store.sessionId
    const base = '/api/review/enhance'
    let endpoint = ''
    let body = { session_id: sessionId }

    if (activeTab.value === 'audio') {
      endpoint = `${base}/audio`
      body = { ...body, denoise: audioDenoise.value, equalizer: audioEqualizer.value, compressor: audioCompressor.value, loudnorm: audioLoudnorm.value }
    } else if (activeTab.value === 'tts') {
      endpoint = `${base}/tts`
      body = { ...body, voice: ttsVoice.value }
    } else if (activeTab.value === 'bgm') {
      endpoint = `${base}/bgm`
      body = { ...body, volume_db: bgmVolume.value, beat_sync: bgmBeatSync.value }
    } else if (activeTab.value === 'transition') {
      endpoint = `${base}/transition`
      body = { ...body, effect: transEffect.value }
    } else if (activeTab.value === 'reframe') {
      endpoint = `${base}/reframe`
      body = { ...body, platform: reframePlatform.value }
    }

    await store._fetch('POST', endpoint, body)
  } finally {
    enhancing.value = false
  }
}
</script>

<template>
  <div class="enhance-panel">
    <div class="enhance-tabs">
      <button
        v-for="tab in tabs" :key="tab.key"
        class="tab-btn" :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="enhance-body">
      <!-- Audio -->
      <div v-if="activeTab === 'audio'" class="enhance-section">
        <label><input type="checkbox" v-model="audioDenoise"> 降噪 (afftdn)</label>
        <label><input type="checkbox" v-model="audioEqualizer"> 均衡器</label>
        <label><input type="checkbox" v-model="audioCompressor"> 压缩器</label>
        <label><input type="checkbox" v-model="audioLoudnorm"> 响度标准化 (-16 LUFS)</label>
      </div>

      <!-- TTS -->
      <div v-if="activeTab === 'tts'" class="enhance-section">
        <label class="field-label">语音角色</label>
        <select v-model="ttsVoice" class="form-select">
          <option v-for="v in ttsVoices" :key="v.value" :value="v.value">{{ v.label }}</option>
        </select>
      </div>

      <!-- BGM -->
      <div v-if="activeTab === 'bgm'" class="enhance-section">
        <label class="field-label">BGM 音量: {{ bgmVolume }}dB</label>
        <input type="range" v-model.number="bgmVolume" min="-30" max="0" step="1">
        <label><input type="checkbox" v-model="bgmBeatSync"> 节拍同步切点</label>
      </div>

      <!-- Transition -->
      <div v-if="activeTab === 'transition'" class="enhance-section">
        <label class="field-label">转场效果</label>
        <select v-model="transEffect" class="form-select">
          <option v-for="e in transEffects" :key="e" :value="e">{{ e }}</option>
        </select>
      </div>

      <!-- Reframe -->
      <div v-if="activeTab === 'reframe'" class="enhance-section">
        <label class="field-label">目标平台</label>
        <select v-model="reframePlatform" class="form-select">
          <option v-for="p in platforms" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>
    </div>

    <button class="btn btn-primary btn-apply" :disabled="enhancing" @click="applyEnhance">
      {{ enhancing ? '处理中…' : '应用增强' }}
    </button>
  </div>
</template>

<style scoped>
.enhance-panel { padding: 12px; }
.enhance-tabs { display: flex; gap: 4px; margin-bottom: 12px; flex-wrap: wrap; }
.tab-btn {
  padding: 4px 10px; border: 1px solid var(--border, #334155);
  background: transparent; color: var(--text, #e2e8f0);
  border-radius: 4px; font-size: 12px; cursor: pointer;
}
.tab-btn.active { background: var(--accent, #3b82f6); border-color: var(--accent); }
.enhance-section { display: flex; flex-direction: column; gap: 8px; }
.enhance-section label { font-size: 13px; display: flex; align-items: center; gap: 6px; }
.field-label { font-size: 12px; color: var(--text-muted, #94a3b8); margin-bottom: 2px; }
.form-select {
  padding: 6px 8px; border: 1px solid var(--border, #334155);
  background: var(--bg-input, #1e293b); color: var(--text); border-radius: 4px;
}
.btn-apply { margin-top: 12px; width: 100%; }
</style>
