<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[1] }}</h3>
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
      <div class="empty-state-text">还没有选题，点击下方按钮生成。</div>
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
import { useWorkflowStore } from '../../stores/workflow.js'
import labels from '../../i18n/labels.js'

const workflow = useWorkflowStore()
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
</style>
