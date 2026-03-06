<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <span class="project-path">{{ appStore.projectDir || '未打开项目' }}</span>
    <AppNav />
  </div>

  <div class="main">
    <!-- 侧栏 -->
    <aside class="sidebar">
      <div class="sidebar-section">
        <div class="sidebar-label">制作</div>
        <div
          class="sidebar-item"
          :class="{ active: currentView === 'workflow' }"
          @click="switchView('workflow')"
        >
          📋 {{ labels.nav.workflow }}
        </div>
        <div
          class="sidebar-item"
          :class="{ active: currentView === 'tools' }"
          @click="switchView('tools')"
        >
          🧰 {{ labels.nav.tools }}
        </div>
      </div>

      <!-- 最近项目 -->
      <div class="sidebar-section">
        <div class="sidebar-label">最近项目</div>
        <div v-if="appStore.recentProjectsLoading" class="sidebar-hint">加载中...</div>
        <div v-else-if="appStore.recentProjects.length === 0" class="sidebar-hint">暂无项目</div>
        <div
          v-for="proj in appStore.recentProjects.slice(0, 8)"
          :key="proj.path"
          class="sidebar-item project-item"
          :class="{ active: proj.path === appStore.projectDir }"
          @click="openRecentProject(proj.path)"
        >
          <span class="project-name">{{ proj.name }}</span>
          <span class="project-status-badge" :class="`status-${proj.status}`">
            {{ statusLabel(proj.status) }}
          </span>
        </div>
      </div>

      <div class="sidebar-section" style="margin-top: auto">
        <div
          class="sidebar-item"
          @click="appStore.showInit = true; appStore.initMode = 'new'"
        >
          ➕ {{ labels.project.new }}
        </div>
        <div
          class="sidebar-item"
          @click="appStore.showInit = true; appStore.initMode = 'open'"
        >
          📂 {{ labels.project.open }}
        </div>
      </div>
    </aside>

    <!-- 内容区 -->
    <div class="content">
      <router-view />

      <!-- 无子路由时显示默认 -->
      <div v-if="!hasChildRoute" class="content-narrow">
        <div class="empty-state">
          <div class="empty-state-icon">🎬</div>
          <div class="empty-state-title">选择一个模块开始</div>
          <div class="empty-state-text">
            从左侧导航选择"工作流"进入制作流程，或选择"工具台"使用独立功能。
          </div>
        </div>
      </div>
    </div>

    <!-- 新建/打开项目弹窗 -->
    <ProjectDialog v-if="appStore.showInit" />
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '../stores/app.js'
import labels from '../i18n/labels.js'
import AppNav from '../components/layout/AppNav.vue'
import ProjectDialog from '../components/common/ProjectDialog.vue'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()

const currentView = computed(() => {
  if (route.name === 'workflow' || route.name === 'workflow-step') return 'workflow'
  if (route.name === 'tools' || route.name === 'tools-tab') return 'tools'
  return ''
})

const hasChildRoute = computed(() => !!currentView.value)

function switchView(view) {
  if (view === 'workflow') {
    router.push('/production/workflow')
  } else if (view === 'tools') {
    router.push('/production/tools')
  }
}

async function openRecentProject(path) {
  await appStore.openProject(path)
}

function statusLabel(status) {
  const map = {
    draft: '草稿',
    in_progress: '进行中',
    completed: '已完成',
    missing: '已删除',
    unknown: '未知',
  }
  return map[status] || status
}

onMounted(() => {
  appStore.loadRecentProjects()
})
</script>

<style scoped>
.project-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.project-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.project-status-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
  font-weight: 500;
}

.status-draft { background: rgba(200,200,200,0.2); color: var(--muted); }
.status-in_progress { background: rgba(90,141,238,0.15); color: var(--accent); }
.status-completed { background: rgba(72,199,142,0.15); color: #48c78e; }
.status-missing { background: rgba(255,100,100,0.15); color: #ff6464; }
.status-unknown { background: rgba(200,200,200,0.15); color: var(--muted); }

.sidebar-hint {
  font-size: 11px;
  color: var(--muted);
  padding: 4px 16px;
}
</style>
