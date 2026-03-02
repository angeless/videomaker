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
import { computed } from 'vue'
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
</script>
