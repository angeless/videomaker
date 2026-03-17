<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[6] }}</h3>
    <p class="text-muted" style="margin-bottom: 16px">
      执行完整渲染流水线：片段合并 → 美颜 → 调色 → 字幕 → 混音 → 成品。
    </p>

    <!-- 完成态 -->
    <div v-if="isDone && workflow.finalUrl" class="card done-card">
      <div class="card-header text-success">🎉 渲染完成</div>
      <video :src="workflow.finalUrl" controls style="width: 100%; border-radius: 6px"></video>
      <div class="done-actions">
        <a :href="workflow.finalUrl" download class="btn btn-primary btn-sm">下载成品</a>
        <button class="btn btn-outline btn-sm" @click="openInFinder">在 Finder 中查看</button>
      </div>
    </div>

    <!-- 渲染阶段进度 -->
    <div v-if="workflow.jobRunning || (showStages && !isDone)" class="render-stages">
      <div v-for="(name, i) in workflow.stageNames" :key="i" class="stage-item">
        <span class="stage-indicator" :class="stageStatus(i)">
          {{ stageIcon(i) }}
        </span>
        <span>{{ name }}</span>
      </div>
    </div>

    <!-- 未完成时的最终结果预览 -->
    <div v-if="!isDone && workflow.finalUrl" class="card" style="margin-top: 16px">
      <div class="card-header text-success">🎉 渲染完成</div>
      <video :src="workflow.finalUrl" controls style="width: 100%; border-radius: 6px"></video>
    </div>

    <div v-if="!isDone" class="step-actions">
      <button class="btn btn-primary" :disabled="workflow.jobRunning" @click="workflow.runStep(7)">
        {{ workflow.jobRunning ? labels.workflow.running : (workflow.finalUrl ? '重新渲染' : '开始渲染') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useWorkflowStore } from '../../stores/workflow.js'
import { useAppStore } from '../../stores/app.js'
import { useApiStore } from '../../stores/api.js'
import labels from '../../i18n/labels.js'

const workflow = useWorkflowStore()
const appStore = useAppStore()
const api = useApiStore()

const isDone = computed(() => {
  const s = (appStore.steps || []).find(s => s.n === 7)
  return s ? s.status === 'done' : false
})

const showStages = computed(() => Object.keys(workflow.stageFiles).length > 0)

function stageStatus(index) {
  if (isDone.value) return 'done'
  const key = `stage_${index + 1}`
  if (workflow.stageFiles[key]) return 'done'
  if (workflow.jobRunning && Object.keys(workflow.stageFiles).length === index) return 'running'
  return 'pending'
}

function stageIcon(index) {
  const status = stageStatus(index)
  if (status === 'done') return '✓'
  if (status === 'running') return '⋯'
  return `${index + 1}`
}

async function openInFinder() {
  await api.api('POST', '/api/open_in_finder', { path: 'output' })
}
</script>

<style scoped>
.step-panel h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.step-actions { display: flex; gap: 10px; margin-top: 16px; }
.render-stages { display: flex; flex-direction: column; gap: 8px; }
.stage-item { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.stage-indicator {
  width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
  background: var(--surface2); border: 1px solid var(--border);
}
.stage-indicator.done { background: var(--success); border-color: transparent; color: #111; }
.stage-indicator.running { background: var(--accent); border-color: transparent; color: #fff; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
.done-card { border-color: var(--success); }
.done-actions { display: flex; gap: 8px; margin-top: 12px; }
.btn-outline {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text);
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}
.btn-outline:hover { background: var(--surface2); }
</style>
