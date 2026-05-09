<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <ProjectTitle />
    <AppNav />
  </div>

  <div class="main">
    <!-- 侧栏 — 双轨制 -->
    <aside class="sidebar">
      <!-- 引导流程 -->
      <div class="sidebar-section">
        <div class="sidebar-label">{{ labels.createSidebar.guided }}</div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('workflow') }"
          @click="go('workflow')"
        >
          📋 {{ labels.createSidebar.guidedWorkflow }}
        </div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('ideate') }"
          @click="go('ideate')"
        >
          💡 {{ labels.createSidebar.ideate }}
        </div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('organize') }"
          @click="go('organize')"
        >
          ✂️ {{ labels.createSidebar.organize }}
        </div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('refine') }"
          @click="go('refine')"
        >
          ✨ {{ labels.createSidebar.refine }}
        </div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('audio') }"
          @click="go('audio')"
        >
          🎵 {{ labels.createSidebar.audio }}
        </div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('subtitle') }"
          @click="go('subtitle')"
        >
          📝 {{ labels.createSidebar.subtitle }}
        </div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('publish') }"
          @click="go('publish')"
        >
          📤 {{ labels.createSidebar.publish }}
        </div>
      </div>

      <!-- 自由创作 -->
      <div class="sidebar-section">
        <div class="sidebar-label">{{ labels.createSidebar.freeform }}</div>
        <div
          class="sidebar-item"
          :class="{ active: isActive('canvas') }"
          @click="go('canvas')"
        >
          🧩 {{ labels.createSidebar.canvas }}
        </div>
        <div class="sidebar-hint" style="padding: 0 8px; font-size: 11px; color: var(--muted)">
          自由组合能力节点，适合非线性或复杂工作流
        </div>
      </div>

      <!-- 最近项目（有项目或正在加载时才显示） -->
      <div v-if="appStore.recentProjectsLoading || validRecentProjects.length > 0" class="sidebar-section">
        <div class="sidebar-label">最近项目</div>
        <div v-if="appStore.recentProjectsLoading" class="sidebar-hint">加载中...</div>
        <div
          v-for="proj in validRecentProjects"
          :key="proj.path"
          class="sidebar-item project-item"
          :class="{ active: proj.path === appStore.projectDir }"
          @click="openRecentProject(proj.path)"
        >
          <span class="project-name" :title="proj.name">{{ humanizeProjectName(proj.name) }}</span>
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
    <div class="content" :class="{ 'content-full': isFullBleed }">
      <router-view />

      <!-- 无项目时显示引导 -->
      <div v-if="!appStore.hasProject && !hasChildRoute" class="content-narrow">
        <div class="empty-state">
          <div class="empty-state-icon">🎬</div>
          <div class="empty-state-title">还没有项目</div>
          <div class="empty-state-text">先导入素材，再新建项目开始创作</div>
          <div class="empty-state-actions">
            <button class="btn btn-primary" @click="appStore.showInit = true; appStore.initMode = 'new'">
              新建项目
            </button>
          </div>
        </div>
      </div>
      <!-- 无子路由时显示默认 -->
      <div v-else-if="!hasChildRoute" class="content-narrow">
        <div class="empty-state">
          <div class="empty-state-icon">🎬</div>
          <div class="empty-state-title">选择一个模块开始</div>
          <div class="empty-state-text">
            从左侧选择"7步工作流"进入引导式创作，或使用"工作流画布"自由组合能力。
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
import ProjectTitle from '../components/common/ProjectTitle.vue'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()

const childRouteNames = [
  'workflow', 'workflow-step', 'tools', 'tools-tab',
  'ideate', 'organize', 'refine', 'audio', 'subtitle', 'publish',
  'canvas',
]

const hasChildRoute = computed(() => childRouteNames.includes(route.name))

// 画布等全出血视图需要去除 .content 的 padding
const isFullBleed = computed(() => route.name === 'canvas')

function isActive(key) {
  const name = route.name || ''
  if (key === 'workflow') return name === 'workflow' || name === 'workflow-step'
  if (key === 'tools') return name === 'tools' || name === 'tools-tab'
  return name === key
}

function go(key) {
  const pathMap = {
    workflow: '/create/guide',
    ideate: '/create/ideate',
    organize: '/create/organize',
    refine: '/create/refine',
    audio: '/create/audio',
    subtitle: '/create/subtitle',
    publish: '/create/publish',
    canvas: '/create/canvas',
  }
  router.push(pathMap[key] || '/create')
}

// C-06: 过滤掉已删除（missing）的项目
const validRecentProjects = computed(() => {
  return (appStore.recentProjects || []).filter(p => p.status !== 'missing').slice(0, 6)
})

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

// B-09: 将机器生成的项目目录名转为可读名称
function humanizeProjectName(name) {
  if (!name) return '未命名项目'
  // 匹配 proj_<type>_<YYYYMMDD>_<HHMMSS> 格式
  const m = name.match(/^proj_(\w+?)_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/)
  if (m) {
    const typeMap = { selected: '精选', draft: '草稿', new: '新建', import: '导入', test: '测试' }
    const label = typeMap[m[1]] || m[1]
    return `${label} ${m[3]}/${m[4]} ${m[5]}:${m[6]}`
  }
  return name
}

onMounted(() => {
  appStore.loadRecentProjects()
  // B-26: 有项目时自动进入 7 步工作流，避免空状态
  if (appStore.projectDir && !hasChildRoute.value) {
    router.replace('/create/guide')
  }
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
