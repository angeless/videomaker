<template>
  <nav class="app-nav">
    <router-link to="/library" class="nav-link" :class="{ active: isActive('library') }">
      {{ labels.nav.library }}
    </router-link>
    <router-link to="/create/guide" class="nav-link" :class="{ active: isActive('create') }">
      {{ labels.nav.create }}
    </router-link>
    <router-link to="/workflows" class="nav-link" :class="{ active: isActive('workflows') }">
      {{ labels.nav.workflow }}
    </router-link>
    <router-link to="/tools" class="nav-link" :class="{ active: isActive('tools') }">
      {{ labels.nav.tools }}
    </router-link>
    <router-link to="/settings" class="nav-link" :class="{ active: isActive('settings') }">
      {{ labels.nav.settings }}
    </router-link>

    <!-- 任务队列指示 -->
    <div v-if="appStore.taskQueue.running_count > 0" class="queue-badge">
      {{ appStore.taskQueue.running_count }} 运行中
      <span v-if="appStore.taskQueue.queued_count > 0">, {{ appStore.taskQueue.queued_count }} 排队</span>
    </div>

    <!-- 通知铃铛 -->
    <NotificationPanel />
  </nav>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import labels from '../../i18n/labels.js'
import NotificationPanel from '../common/NotificationPanel.vue'

const route = useRoute()
const appStore = useAppStore()

function isActive(section) {
  const name = route.name || ''
  if (section === 'library') return name === 'library'
  if (section === 'create') return ['create', 'workflow', 'workflow-step', 'ideate', 'organize', 'refine', 'audio', 'subtitle', 'publish', 'canvas'].includes(name)
  if (section === 'workflows') return name === 'workflow-manager'
  if (section === 'tools') return ['tools', 'tools-tab'].includes(name)
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
