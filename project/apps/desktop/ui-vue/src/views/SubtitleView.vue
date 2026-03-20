<template>
  <div class="subtitle-view">
    <div class="view-header">
      <h2>{{ labels.createSidebar.subtitle }}</h2>
      <p class="view-desc">中英文字幕和时间轴</p>
    </div>
    <div class="subtitle-content">
      <SubtitleCalibration />
    </div>
  </div>
</template>

<script setup>
import labels from '../i18n/labels.js'
import SubtitleCalibration from '../components/capabilities/SubtitleCalibration.vue'
</script>

<style scoped>
.subtitle-view {
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

.subtitle-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
</style>
