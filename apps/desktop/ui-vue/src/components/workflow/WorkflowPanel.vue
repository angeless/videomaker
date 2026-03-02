<template>
  <div class="workflow-panel">
    <!-- 步骤条 -->
    <WorkflowStepper
      :steps="workflow.stepLabels"
      :current="appStore.currentStep"
      :active="currentStepNum"
      @select="goToStep"
    />

    <!-- 运行状态栏 -->
    <div v-if="workflow.jobRunning" class="step-status-bar">
      <div class="ai-spinner">
        {{ labels.workflow.running }}（{{ Math.round(workflow.jobProgress) }}%）
      </div>
      <div class="progress-bar" style="margin-top: 8px">
        <div class="progress-bar-fill" :style="{ width: workflow.jobProgress + '%' }"></div>
      </div>
    </div>

    <!-- 步骤面板 -->
    <div class="step-content">
      <component :is="stepComponent" />
    </div>

    <!-- 日志（运行时显示） -->
    <LogViewer
      v-if="workflow.jobLog.length > 0"
      :lines="formattedLog"
      style="margin-top: 16px"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import { useWorkflowStore } from '../../stores/workflow.js'
import labels from '../../i18n/labels.js'
import WorkflowStepper from './WorkflowStepper.vue'
import LogViewer from '../common/LogViewer.vue'
import Step1Materials from './Step1Materials.vue'
import Step2Topics from './Step2Topics.vue'
import Step3Script from './Step3Script.vue'
import Step4Match from './Step4Match.vue'
import Step5Frames from './Step5Frames.vue'
import Step6Rough from './Step6Rough.vue'
import Step7Render from './Step7Render.vue'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const workflow = useWorkflowStore()

const currentStepNum = computed(() => {
  const param = route.params.step
  if (param) return Number(param) || 1
  return appStore.currentStep || 1
})

const stepComponent = computed(() => {
  const s = currentStepNum.value
  const map = {
    1: Step1Materials,
    2: Step2Topics,
    3: Step3Script,
    4: Step4Match,
    5: Step5Frames,
    6: Step6Rough,
    7: Step7Render,
  }
  return map[s] || Step1Materials
})

const formattedLog = computed(() => {
  return workflow.jobLog.map(entry => {
    if (typeof entry === 'string') return entry
    if (entry.message) return `${entry.timestamp || ''} ${entry.message}`
    return JSON.stringify(entry)
  })
})

function goToStep(stepNum) {
  router.push(`/production/workflow/${stepNum}`)
}
</script>

<style scoped>
.workflow-panel {
  padding: 0 24px 24px;
}

.step-status-bar {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}

.step-content {
  min-height: 300px;
}
</style>
