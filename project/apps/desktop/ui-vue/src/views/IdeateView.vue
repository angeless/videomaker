<template>
  <div class="ideate-view">
    <div class="view-header">
      <h2>{{ labels.createSidebar.ideate }}</h2>
      <p class="view-desc">浏览选题模板，生成文案草稿</p>
    </div>
    <div class="ideate-panels">
      <div class="ideate-panel">
        <TopicLibrary />
      </div>
      <div class="ideate-panel">
        <TopicCopy />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, provide } from 'vue'
import labels from '../i18n/labels.js'
import TopicLibrary from '../components/capabilities/TopicLibrary.vue'
import TopicCopy from '../components/capabilities/TopicCopy.vue'

const selectedSlug = ref('')
provide('ideateSelectedSlug', selectedSlug)
</script>

<style scoped>
.ideate-view {
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

.ideate-panels {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-height: 0;
}

.ideate-panel {
  flex: 1;
  min-height: 200px;
  overflow-y: auto;
}
</style>
