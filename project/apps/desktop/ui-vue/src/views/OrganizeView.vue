<template>
  <div class="organize-view">
    <div class="view-header">
      <h2>{{ labels.createSidebar.organize }}</h2>
      <p class="view-desc">按句子删减控制时长，规划精华片段</p>
    </div>
    <div class="organize-panels">
      <div class="organize-left">
        <div class="panel-section">
          <TextRoughCut />
        </div>
        <div class="panel-section">
          <ShortClip />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import labels from '../i18n/labels.js'
import TextRoughCut from '../components/capabilities/TextRoughCut.vue'
import ShortClip from '../components/capabilities/ShortClip.vue'
</script>

<style scoped>
.organize-view {
  max-width: 900px;
}

.view-header {
  margin-bottom: 20px;
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

.organize-panels {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
</style>
