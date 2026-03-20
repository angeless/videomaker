<template>
  <div class="publish-view">
    <div class="view-header">
      <h2>{{ labels.createSidebar.publish }}</h2>
      <p class="view-desc">生成发布文案、多平台导出、一键发布</p>
    </div>

    <!-- 三步 tab 切换 -->
    <div class="publish-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="publish-tab"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="publish-content">
      <PublishPrep v-if="activeTab === 'prep'" />
      <SocialExport v-if="activeTab === 'export'" />
      <ContentPublish v-if="activeTab === 'publish'" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import labels from '../i18n/labels.js'
import PublishPrep from '../components/capabilities/PublishPrep.vue'
import SocialExport from '../components/capabilities/SocialExport.vue'
import ContentPublish from '../components/capabilities/ContentPublish.vue'

const activeTab = ref('prep')
const tabs = [
  { key: 'prep', label: '发布文案' },
  { key: 'export', label: '社媒导出' },
  { key: 'publish', label: '内容发布' },
]
</script>

<style scoped>
.publish-view {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.view-header {
  margin-bottom: 16px;
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

.publish-tabs {
  display: flex;
  gap: 2px;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.publish-tab {
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.publish-tab:hover {
  background: var(--surface2);
  color: var(--text);
}

.publish-tab.active {
  background: rgba(90, 141, 238, 0.1);
  color: var(--accent);
  font-weight: 500;
}

.publish-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
</style>
