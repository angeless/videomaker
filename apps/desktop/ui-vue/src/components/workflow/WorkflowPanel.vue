<template>
  <div class="workflow-panel">
    <!-- 步骤条 -->
    <WorkflowStepper
      :steps="workflow.stepLabels"
      :current="effectiveCurrent"
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

    <!-- 引导式工作流暂未就绪提示 -->
    <div v-if="!workflow.guidedAvailable" class="workflow-unavailable-banner">
      <strong>引导式工作流暂未连接</strong>
      <p>后端步骤引擎尚未启用。你可以直接使用左侧「选题构思」「剪辑编排」等独立模块完成创作。</p>
    </div>

    <!-- 步骤面板 -->
    <div class="step-content">
      <component :is="stepComponent" />
    </div>

    <!-- 时间线（步骤 3+ 且有脚本数据时显示） -->
    <TimelinePanel v-if="showTimeline" />

    <!-- 日志（运行时显示） -->
    <LogViewer
      v-if="workflow.jobLog.length > 0"
      :lines="formattedLog"
      style="margin-top: 16px"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
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
import TimelinePanel from '../timeline/TimelinePanel.vue'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const workflow = useWorkflowStore()

const currentStepNum = computed(() => {
  const param = route.params.step
  if (param) return Number(param) || 1
  return appStore.currentStep || 1
})

// Stepper 用的 "frontier" — 保证已完成的步骤都显示 ✓
// 规则：取 backend current_step 与 最高已完成步骤+1 的较大值
const effectiveCurrent = computed(() => {
  const backendCurrent = appStore.currentStep || 1
  const stepsList = appStore.steps || []
  let highestDone = 0
  for (const s of stepsList) {
    if (s.status === 'done' && s.n > highestDone) highestDone = s.n
  }
  return Math.max(backendCurrent, highestDone + 1)
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

const showTimeline = computed(() => {
  return currentStepNum.value >= 3 && (workflow.scriptClips?.length > 0)
})

const formattedLog = computed(() => {
  return workflow.jobLog.map(entry => {
    if (typeof entry === 'string') return entry
    if (entry.message) return `${entry.timestamp || ''} ${entry.message}`
    return JSON.stringify(entry)
  })
})

function goToStep(stepNum) {
  router.push(`/create/workflow/${stepNum}`)
}

// 进入工作流时加载步骤数据（roughUrl / finalUrl / stageFiles 等）
onMounted(() => {
  if (appStore.projectDir) workflow.loadStepData()
})
watch(() => appStore.projectDir, (dir) => {
  if (dir) workflow.loadStepData()
})
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

.workflow-unavailable-banner {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text);
}

.workflow-unavailable-banner strong {
  display: block;
  margin-bottom: 4px;
  color: #b45309;
}

.workflow-unavailable-banner p {
  margin: 0;
  color: var(--muted);
  line-height: 1.5;
}
</style>
