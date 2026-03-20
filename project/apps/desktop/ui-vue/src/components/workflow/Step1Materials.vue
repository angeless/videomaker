<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[0] }}</h3>

    <div v-if="stepDone" class="step-done-banner">
      <span>✅ 素材分析已完成
        <span v-if="workflow.selectedAssets.length > 0">— {{ workflow.selectedAssets.length }} 个素材已就绪</span>
      </span>
      <button class="btn btn-sm btn-next" @click="router.push('/create/workflow/2')">继续下一步 →</button>
    </div>

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
        {{ workflow.jobRunning ? labels.workflow.running : '分析素材' }}
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
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import { useWorkflowStore } from '../../stores/workflow.js'
import labels from '../../i18n/labels.js'

const router = useRouter()
const appStore = useAppStore()
const workflow = useWorkflowStore()

const stepDone = computed(() => {
  const s = (appStore.steps || []).find(s => s.n === 1)
  return s ? s.status === 'done' : false
})
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
