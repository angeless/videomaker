<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[3] }}</h3>
    <p class="text-muted" style="margin-bottom: 16px">
      系统自动将脚本中的分镜与素材库中的视频片段进行匹配。
    </p>

    <div class="step-actions">
      <button class="btn btn-primary" :disabled="workflow.jobRunning" @click="workflow.runStep(4)">
        {{ workflow.jobRunning ? labels.workflow.running : '开始匹配' }}
      </button>
      <button v-if="appStore.currentStep > 4" class="btn btn-success" @click="workflow.approveStep(4)">
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
.step-panel h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.step-actions { display: flex; gap: 10px; margin-top: 16px; }
</style>
