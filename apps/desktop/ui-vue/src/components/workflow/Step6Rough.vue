<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[5] }}</h3>
    <p class="text-muted" style="margin-bottom: 16px">
      生成粗剪视频，用于快速预览整体效果。
    </p>

    <!-- 渲染选项 -->
    <div class="card" style="margin-bottom: 16px">
      <div class="card-header">渲染参数</div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px">
        <div class="form-group">
          <label class="form-label">目标时长（秒）</label>
          <input v-model.number="workflow.renderOpts.rough_target_seconds" class="form-input" type="number" />
        </div>
        <div class="form-group">
          <label class="form-label">最大片段数</label>
          <input v-model.number="workflow.renderOpts.rough_max_clips" class="form-input" type="number" />
        </div>
        <div class="form-group">
          <label class="form-label">转场风格</label>
          <select v-model="workflow.renderOpts.transition_style" class="form-select">
            <option value="fade">淡入淡出</option>
            <option value="cut">硬切</option>
            <option value="dissolve">溶解</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">美颜强度</label>
          <input v-model.number="workflow.renderOpts.skin_smooth_strength" class="form-input" type="number" step="0.1" min="0" max="1" />
        </div>
      </div>
    </div>

    <!-- 粗剪结果 -->
    <div v-if="workflow.roughUrl" class="card">
      <div class="card-header">粗剪结果</div>
      <video :src="workflow.roughUrl" controls style="width: 100%; border-radius: 6px"></video>
    </div>

    <div class="step-actions">
      <button class="btn btn-primary" :disabled="workflow.jobRunning" @click="workflow.runStep(6)">
        {{ workflow.jobRunning ? labels.workflow.running : '生成粗剪' }}
      </button>
      <button v-if="workflow.roughUrl" class="btn btn-success" @click="workflow.approveStep(6)">
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
</style>
