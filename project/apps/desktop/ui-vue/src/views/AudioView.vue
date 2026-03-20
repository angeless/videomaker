<template>
  <div class="audio-view">
    <div class="view-header">
      <h2>{{ labels.createSidebar.audio }}</h2>
      <p class="view-desc">旁白、BGM 和混音</p>
    </div>
    <div class="audio-content">
      <AudioVoice />
    </div>
  </div>
</template>

<script setup>
import labels from '../i18n/labels.js'
import AudioVoice from '../components/capabilities/AudioVoice.vue'
</script>

<style scoped>
.audio-view {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.view-header {
  margin-bottom: 20px;
  flex-shrink: 0;
}

.view-header h2 {
  margin: 0 0 4px 0;
  font-size: 18px;
}

.view-desc {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
}

.audio-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: 48px;
}
</style>
