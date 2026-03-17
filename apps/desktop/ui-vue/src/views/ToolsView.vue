<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <span class="project-path" :title="appStore.projectDir">{{ projectDisplayName }}</span>
    <AppNav />
  </div>

  <div class="main">
    <div class="content" style="padding: 0">
      <CapabilityLayout />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAppStore } from '../stores/app.js'
import labels from '../i18n/labels.js'
import AppNav from '../components/layout/AppNav.vue'
import CapabilityLayout from '../components/capabilities/CapabilityLayout.vue'

const appStore = useAppStore()

const projectDisplayName = computed(() => {
  const dir = appStore.projectDir
  if (!dir) return '未打开项目'
  const name = dir.split('/').filter(Boolean).pop() || dir
  const m = name.match(/^proj_selected_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/)
  if (m) return `项目 ${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`
  return name
})
</script>
