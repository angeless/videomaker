<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[3] }}</h3>

    <div v-if="stepDone" class="step-done-banner">
      <span>✅ 素材匹配已完成</span>
      <button class="btn btn-sm btn-next" @click="router.push('/create/guide/5')">继续下一步 →</button>
    </div>

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
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import { useWorkflowStore } from '../../stores/workflow.js'
import labels from '../../i18n/labels.js'
const router = useRouter()
const appStore = useAppStore()
const workflow = useWorkflowStore()

const stepDone = computed(() => {
  const s = (appStore.steps || []).find(s => s.n === 4)
  return s ? s.status === 'done' : false
})
</script>

<style scoped>
.step-panel h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.step-actions { display: flex; gap: 10px; margin-top: 16px; }
.step-done-banner {
  background: rgba(52, 211, 153, 0.1);
  border: 1px solid rgba(52, 211, 153, 0.3);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--success, #34d399);
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.btn-next {
  background: var(--accent);
  color: #fff;
  border: none;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
}
</style>
