<template>
  <div id="app-root">
    <router-view />
    <ToastContainer />
    <OnboardingModal v-if="appStore.showOnboardingWizard" />
  </div>
</template>

<script setup>
import { useAppStore } from './stores/app.js'
import ToastContainer from './components/common/ToastContainer.vue'
import OnboardingModal from './components/onboarding/OnboardingModal.vue'

const appStore = useAppStore()
</script>
