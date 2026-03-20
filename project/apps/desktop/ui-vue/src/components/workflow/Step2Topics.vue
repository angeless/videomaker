<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[1] }}</h3>

    <div v-if="stepDone" class="step-done-banner">
      <span>✅ 选题已确定<span v-if="selectedTitle"> — {{ selectedTitle }}</span></span>
      <button class="btn btn-sm btn-next" @click="router.push('/create/workflow/3')">继续下一步 →</button>
    </div>

    <p class="text-muted" style="margin-bottom: 16px">
      AI 根据你的素材内容生成选题建议，选择一个作为本次创作方向。
    </p>

    <!-- 选题列表 -->
    <div v-if="workflow.topics.length > 0" class="topics-list">
      <div
        v-for="(topic, i) in workflow.topics"
        :key="i"
        class="topic-item card"
        :class="{ 'topic-selected': workflow.selectedTopic === i }"
        @click="workflow.selectedTopic = i"
      >
        <div class="topic-title">{{ topic.title || topic }}</div>
        <div v-if="topic.description" class="topic-desc text-muted">{{ topic.description }}</div>
      </div>
    </div>

    <div v-else class="empty-state" style="padding: 24px">
      <div v-if="stepDone" class="empty-state-text">选题数据已归档，可重新生成或继续下一步。</div>
      <div v-else class="empty-state-text">还没有选题，点击下方按钮生成。</div>
    </div>

    <div class="step-actions">
      <button
        class="btn btn-primary"
        :disabled="workflow.jobRunning"
        @click="workflow.runStep(2)"
      >
        {{ workflow.jobRunning ? labels.workflow.running : '生成选题' }}
      </button>
      <button
        v-if="workflow.topics.length > 0 && workflow.selectedTopic !== null"
        class="btn btn-success"
        @click="workflow.approveStep(2)"
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
  const s = (appStore.steps || []).find(s => s.n === 2)
  return s ? s.status === 'done' : false
})
const selectedTitle = computed(() => {
  if (workflow.selectedTopic !== null && workflow.topics[workflow.selectedTopic]) {
    const t = workflow.topics[workflow.selectedTopic]
    return t.title || t
  }
  return ''
})
</script>

<style scoped>
.step-panel h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.step-actions { display: flex; gap: 10px; margin-top: 16px; }
.topics-list { display: flex; flex-direction: column; gap: 8px; }
.topic-item { cursor: pointer; transition: border-color 0.15s; }
.topic-item:hover { border-color: var(--accent); }
.topic-selected { border-color: var(--accent); background: rgba(90, 141, 238, 0.05); }
.topic-title { font-weight: 500; margin-bottom: 4px; }
.topic-desc { font-size: 12px; }
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
