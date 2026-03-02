<template>
  <nav class="app-nav">
    <router-link to="/library" class="nav-link" :class="{ active: isActive('library') }">
      {{ labels.nav.library }}
    </router-link>
    <router-link to="/production/workflow" class="nav-link" :class="{ active: isActive('production') }">
      {{ labels.nav.production }}
    </router-link>
    <router-link to="/settings" class="nav-link" :class="{ active: isActive('settings') }">
      {{ labels.nav.settings }}
    </router-link>

    <!-- 任务队列指示 -->
    <div v-if="appStore.taskQueue.running_count > 0" class="queue-badge">
      {{ appStore.taskQueue.running_count }} 运行中
      <span v-if="appStore.taskQueue.queued_count > 0">, {{ appStore.taskQueue.queued_count }} 排队</span>
    </div>
  </nav>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import labels from '../../i18n/labels.js'

const route = useRoute()
const appStore = useAppStore()

function isActive(section) {
  const name = route.name || ''
  if (section === 'library') return name === 'library'
  if (section === 'production') return ['production', 'workflow', 'workflow-step', 'tools', 'tools-tab'].includes(name)
  if (section === 'settings') return name === 'settings'
  return false
}
</script>

<style scoped>
.app-nav {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}

.nav-link {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--muted);
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}

.nav-link:hover {
  background: var(--surface2);
  color: var(--text);
  text-decoration: none;
}

.nav-link.active {
  background: var(--accent);
  color: #fff;
}

.queue-badge {
  margin-left: 8px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  background: rgba(90, 141, 238, 0.15);
  color: var(--accent);
  border: 1px solid var(--accent);
}
</style>
