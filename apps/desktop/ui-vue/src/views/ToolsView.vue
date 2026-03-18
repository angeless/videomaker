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
import { useFormatters } from '../composables/useFormatters.js'
import labels from '../i18n/labels.js'
import AppNav from '../components/layout/AppNav.vue'
import CapabilityLayout from '../components/capabilities/CapabilityLayout.vue'

const appStore = useAppStore()
const { humanizeProjectDir } = useFormatters()

const projectDisplayName = computed(() => humanizeProjectDir(appStore.projectDir))
</script>
