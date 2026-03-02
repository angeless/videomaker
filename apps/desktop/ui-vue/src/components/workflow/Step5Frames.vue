<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[4] }}</h3>
    <p class="text-muted" style="margin-bottom: 16px">
      预览每个分镜对应的关键帧，确认素材匹配是否正确。
    </p>

    <div v-if="workflow.frames.length > 0" class="frames-grid">
      <div v-for="(frame, i) in workflow.frames" :key="i" class="frame-card card">
        <div class="frame-thumb">
          <img v-if="frame.thumbnail" :src="frame.thumbnail" :alt="`帧 ${i + 1}`" />
          <div v-else class="frame-placeholder">🎞️</div>
        </div>
        <div class="frame-info">
          <span class="frame-num">#{{ i + 1 }}</span>
          <span v-if="frame.video_id" class="text-muted" style="font-size: 11px">{{ frame.video_id }}</span>
        </div>
      </div>
    </div>

    <div v-else class="empty-state" style="padding: 24px">
      <div class="empty-state-text">还没有帧预览数据。</div>
    </div>

    <div class="step-actions">
      <button class="btn btn-primary" :disabled="workflow.jobRunning" @click="workflow.runStep(5)">
        {{ workflow.jobRunning ? labels.workflow.running : '生成预览' }}
      </button>
      <button v-if="workflow.frames.length > 0" class="btn btn-success" @click="workflow.approveStep(5)">
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
.frames-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; }
.frame-card { padding: 0; overflow: hidden; }
.frame-thumb { height: 90px; background: var(--bg); display: flex; align-items: center; justify-content: center; }
.frame-thumb img { width: 100%; height: 100%; object-fit: cover; }
.frame-placeholder { font-size: 24px; opacity: 0.3; }
.frame-info { padding: 6px 8px; display: flex; gap: 6px; align-items: center; }
.frame-num { font-size: 11px; font-weight: 600; color: var(--accent); }
</style>
