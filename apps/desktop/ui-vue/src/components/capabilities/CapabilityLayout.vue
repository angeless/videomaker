<template>
  <div class="capability-layout">
    <!-- 左侧导航 -->
    <aside class="capability-nav">
      <div v-for="group in capStore.groups" :key="group.key" class="cap-group">
        <div class="cap-group-title">{{ group.title }}</div>
        <div
          v-for="item in group.items"
          :key="item.tab"
          class="cap-item"
          :class="{ active: currentTab === item.tab }"
          @click="selectTab(item.tab)"
        >
          <span class="cap-item-label">{{ item.label }}</span>
          <span class="cap-item-hint text-muted">{{ item.hint }}</span>
        </div>
      </div>
    </aside>

    <!-- 右侧面板 -->
    <div class="capability-content">
      <!-- 消息提示 -->
      <div v-if="capStore.message" class="badge" :class="`badge-${capStore.messageType}`" style="margin-bottom: 12px">
        {{ capStore.message }}
      </div>

      <!-- 面板内容 -->
      <div class="cap-panel">
        <CapabilityPlaceholder :tab="currentTab" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import CapabilityPlaceholder from './CapabilityPlaceholder.vue'

const route = useRoute()
const router = useRouter()
const capStore = useCapabilitiesStore()

const currentTab = computed(() => {
  return route.params.tab || capStore.activeTab || 'topic_library'
})

function selectTab(tab) {
  capStore.activeTab = tab
  router.push(`/production/tools/${tab}`)
}
</script>

<style scoped>
.capability-layout {
  display: flex;
  height: 100%;
}

.capability-nav {
  width: 200px;
  border-right: 1px solid var(--border);
  padding: 16px 0;
  overflow-y: auto;
  flex-shrink: 0;
}

.cap-group {
  margin-bottom: 16px;
}

.cap-group-title {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--muted);
  letter-spacing: 0.08em;
  padding: 0 16px;
  margin-bottom: 4px;
}

.cap-item {
  display: flex;
  flex-direction: column;
  padding: 6px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.cap-item:hover {
  background: var(--surface2);
}

.cap-item.active {
  background: rgba(90, 141, 238, 0.1);
  border-left: 3px solid var(--accent);
}

.cap-item-label {
  font-size: 13px;
  font-weight: 500;
}

.cap-item-hint {
  font-size: 11px;
}

.capability-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
</style>
