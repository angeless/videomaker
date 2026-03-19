<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <ProjectTitle />
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
import ProjectTitle from '../components/common/ProjectTitle.vue'
import CapabilityLayout from '../components/capabilities/CapabilityLayout.vue'

const appStore = useAppStore()
</script>
