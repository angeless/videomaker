<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[0] }}</h3>
    <p class="text-muted" style="margin-bottom: 16px">
      从素材库中选择要用于本次制作的视频素材（最多 {{ workflow.maxSelectedAssets }} 个）。
    </p>

    <div v-if="workflow.selectedAssets.length > 0" class="selected-summary">
      <span class="badge badge-info">已选 {{ workflow.selectedAssets.length }} 个素材</span>
    </div>

    <div class="step-actions">
      <button
        class="btn btn-primary"
        :disabled="workflow.jobRunning"
        @click="workflow.runStep(1)"
      >
        {{ workflow.jobRunning ? labels.workflow.running : labels.workflow.run }}
      </button>
      <button
        v-if="appStore.currentStep > 1"
        class="btn btn-success"
        @click="workflow.approveStep(1)"
      >
        {{ labels.workflow.approve }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { useAppStore } from '../../stores/app.js'
import { useWorkflowStore } from '../../stores/workflow.js'
import labels from '../../i18n/labels.js'

const appStore = useAppStore()
const workflow = useWorkflowStore()
</script>

<style scoped>
.step-panel h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.step-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.selected-summary {
  margin-bottom: 12px;
}
</style>
