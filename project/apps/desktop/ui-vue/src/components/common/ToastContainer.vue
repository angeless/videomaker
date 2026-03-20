<template>
  <Teleport to="body">
    <div v-if="toastStore.toasts.length > 0" class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="t in toastStore.toasts"
          :key="t.id"
          class="toast"
          :class="`toast-${t.type || 'info'}`"
          @click="toastStore.dismiss(t.id)"
        >
          {{ t.message }}
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useToastStore } from '../../stores/toast.js'

const toastStore = useToastStore()
</script>

<style scoped>
.toast-enter-active {
  animation: toast-in 0.25s ease-out;
}
.toast-leave-active {
  animation: toast-in 0.2s ease-in reverse;
}
</style>
