<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[2] }}</h3>

    <div v-if="stepDone" class="step-done-banner">
      <span>✅ 脚本已确认<span v-if="workflow.scriptClips.length > 0"> — {{ workflow.scriptClips.length }} 个分镜</span></span>
      <button class="btn btn-sm btn-next" @click="router.push('/create/guide/4')">继续下一步 →</button>
    </div>

    <p class="text-muted" style="margin-bottom: 16px">
      AI 根据选题和素材生成视频脚本，包含分镜和字幕。
    </p>

    <!-- AI 生成中 -->
    <div v-if="workflow.jobRunning" class="ai-generating">
      <div class="ai-spinner">AI 正在生成脚本…</div>
      <div class="progress-bar" style="margin-top: 12px">
        <div class="progress-bar-fill" :style="{ width: workflow.jobProgress + '%' }"></div>
      </div>
      <p class="text-muted" style="font-size: 12px; margin-top: 8px">
        脚本生成通常需要 30-60 秒，请耐心等待
      </p>
    </div>

    <!-- 脚本内容 -->
    <div v-else-if="workflow.scriptClips.length > 0" class="script-content">
      <div class="form-row" style="margin-bottom: 12px">
        <button
          class="btn btn-sm"
          :class="workflow.scriptView === 'visual' ? 'btn-primary' : 'btn-ghost'"
          @click="workflow.scriptView = 'visual'"
        >
          可视化
        </button>
        <button
          class="btn btn-sm"
          :class="workflow.scriptView === 'json' ? 'btn-primary' : 'btn-ghost'"
          @click="workflow.scriptView = 'json'"
        >
          JSON
        </button>
      </div>

      <!-- 可视化视图 -->
      <div v-if="workflow.scriptView === 'visual'" class="clips-list">
        <div v-for="(clip, i) in workflow.scriptClips" :key="i" class="clip-card card">
          <div class="clip-num">#{{ i + 1 }}</div>
          <div class="clip-info">
            <div v-if="clip.video_id" class="text-muted" style="font-size: 12px">{{ clip.video_id }}</div>
            <div v-if="clip.subtitle || clip.narration" style="margin-top: 4px">
              {{ clip.subtitle || clip.narration }}
            </div>
            <div v-if="clip.duration" class="text-muted" style="font-size: 11px; margin-top: 2px">
              时长 {{ clip.duration }}s
            </div>
          </div>
        </div>
      </div>

      <!-- JSON 视图 -->
      <textarea
        v-else
        v-model="workflow.scriptJson"
        class="form-textarea"
        style="min-height: 200px; font-family: monospace; font-size: 12px"
        readonly
      ></textarea>
    </div>

    <div v-else class="empty-state" style="padding: 24px">
      <div class="empty-state-text">还没有脚本，点击下方按钮生成。</div>
    </div>

    <div class="step-actions">
      <button
        class="btn btn-primary"
        :disabled="workflow.jobRunning"
        @click="workflow.runStep(3)"
      >
        {{ workflow.jobRunning ? labels.workflow.running : '生成脚本' }}
      </button>
      <button
        v-if="workflow.scriptClips.length > 0"
        class="btn btn-success"
        @click="workflow.approveStep(3)"
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
  const s = (appStore.steps || []).find(s => s.n === 3)
  return s ? s.status === 'done' : false
})
</script>

<style scoped>
.step-panel h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.step-actions { display: flex; gap: 10px; margin-top: 16px; }
.ai-generating { padding: 24px; text-align: center; }
.clips-list { display: flex; flex-direction: column; gap: 8px; }
.clip-card { display: flex; gap: 12px; align-items: flex-start; }
.clip-num { font-size: 12px; font-weight: 600; color: var(--accent); min-width: 24px; }
.clip-info { flex: 1; }
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
