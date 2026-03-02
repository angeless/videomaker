import { createRouter, createWebHashHistory } from 'vue-router'

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
  {
    path: '/production',
    name: 'production',
    component: () => import('../views/ProductionView.vue'),
    children: [
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
        path: 'tools',
        name: 'tools',
        component: () => import('../components/capabilities/CapabilityLayout.vue'),
      },
      {
        path: 'tools/:tab',
        name: 'tools-tab',
        component: () => import('../components/capabilities/CapabilityLayout.vue'),
      },
    ],
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
