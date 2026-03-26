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
          <span>{{ t.message }}</span>
          <button
            v-if="t.action"
            class="toast-action"
            @click.stop="t.action.handler(); toastStore.dismiss(t.id)"
          >{{ t.action.label }}</button>
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
.toast-action {
  margin-left: 12px;
  padding: 2px 10px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.toast-action:hover {
  background: rgba(255,255,255,0.15);
}
</style>
