import { createRouter, createWebHashHistory } from 'vue-router'
import { useToastStore } from '../stores/toast.js'

const routes = [
  {
    path: '/',
    name: 'startup',
    component: () => import('../views/StartupView.vue'),
  },
  {
    path: '/library',
    name: 'library',
    component: () => import('../views/LibraryView.vue'),
  },
  // ── 创作主视图（双轨制） ──
  {
    path: '/create',
    name: 'create',
    component: () => import('../views/CreateView.vue'),
    children: [
      // 引导流程
      {
        path: 'workflow',
        name: 'workflow',
        component: () => import('../components/workflow/WorkflowPanel.vue'),
      },
      {
        path: 'workflow/:step',
        name: 'workflow-step',
        component: () => import('../components/workflow/WorkflowPanel.vue'),
      },
      {
        path: 'ideate',
        name: 'ideate',
        component: () => import('../views/IdeateView.vue'),
      },
      {
        path: 'organize',
        name: 'organize',
        component: () => import('../views/OrganizeView.vue'),
      },
      {
        path: 'refine',
        name: 'refine',
        component: () => import('../views/RefineView.vue'),
      },
      {
        path: 'audio',
        name: 'audio',
        component: () => import('../views/AudioView.vue'),
      },
      {
        path: 'subtitle',
        name: 'subtitle',
        component: () => import('../views/SubtitleView.vue'),
      },
      {
        path: 'publish',
        name: 'publish',
        component: () => import('../views/PublishView.vue'),
      },
      // 自由创作
      {
        path: 'canvas',
        name: 'canvas',
        component: () => import('../views/CanvasView.vue'),
      },
    ],
  },
  // ── 工作流管理 ──
  {
    path: '/workflows',
    name: 'workflow-manager',
    component: () => import('../views/WorkflowManagerView.vue'),
  },
  // ── 工具箱（独立入口） ──
  {
    path: '/tools',
    name: 'tools',
    component: () => import('../views/ToolsView.vue'),
  },
  {
    path: '/tools/:tab',
    name: 'tools-tab',
    component: () => import('../views/ToolsView.vue'),
  },
  // ── 设置 ──
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
  },
  // ── 旧路由重定向 ──
  {
    path: '/production',
    redirect: '/create',
  },
  {
    path: '/production/workflow',
    redirect: '/create/workflow',
  },
  {
    path: '/production/workflow/:step',
    redirect: to => `/create/workflow/${to.params.step}`,
  },
  {
    path: '/production/tools',
    redirect: '/tools',
  },
  {
    path: '/production/tools/:tab',
    redirect: to => `/tools/${to.params.tab}`,
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 预检 error 路由守卫：有未确认的 error 时阻止离开 startup
router.beforeEach((to, from) => {
  if (to.name === 'startup') return true
  try {
    const { useAppStore } = require('../stores/app.js')
    const appStore = useAppStore()
    if (appStore.preflightErrorCount > 0 && !appStore.preflightAcknowledged) {
      // 阻止导航，由 StartupView 的弹窗处理
      return { name: 'startup' }
    }
  } catch {
    // pinia not ready during initial load — allow navigation
  }
  return true
})

// 跨页面导航时清理 toast，防止上一页的提示残留
router.afterEach((to, from) => {
  const toTop = (to.path || '').split('/').slice(0, 3).join('/')
  const fromTop = (from.path || '').split('/').slice(0, 3).join('/')
  if (toTop !== fromTop) {
    try { useToastStore().clearAll() } catch { /* pinia not ready */ }
  }
})

export default router
