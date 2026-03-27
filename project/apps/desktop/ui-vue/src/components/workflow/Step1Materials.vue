<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[0] }}</h3>

    <div v-if="stepDone" class="step-done-banner">
      <span>✅ 素材分析已完成
        <span v-if="workflow.selectedAssets.length > 0">— {{ workflow.selectedAssets.length }} 个素材已就绪</span>
      </span>
      <button class="btn btn-sm btn-next" @click="router.push('/create/workflow/2')">继续下一步 →</button>
    </div>

    <!-- 素材来源面板 -->
    <div v-if="!stepDone" class="material-source">
      <!-- Loading skeleton -->
      <div v-if="statsLoading" class="source-card skeleton">
        <div class="skeleton-line w60"></div>
        <div class="skeleton-line w40"></div>
      </div>

      <!-- 空态：无素材 -->
      <div v-else-if="libStats.total_assets === 0" class="source-card empty-state">
        <div class="empty-icon">📂</div>
        <p class="empty-title">素材库为空</p>
        <p class="text-muted">请先导入视频或图片素材，然后回来开始分析</p>
        <button class="btn btn-primary" @click="router.push('/library')">去导入素材</button>
      </div>

      <!-- 有素材：摘要卡片 -->
      <div v-else class="source-card">
        <div class="source-header">
          <span class="badge badge-success">素材库：{{ libStats.total_assets }} 个素材</span>
        </div>
        <p class="text-muted" style="margin: 8px 0">
          从素材库中选择要用于本次制作的视频素材（最多 {{ workflow.maxSelectedAssets }} 个）。
        </p>

        <div v-if="workflow.selectedAssets.length > 0" class="selected-summary">
          <span class="badge badge-info">已选 {{ workflow.selectedAssets.length }} 个素材</span>
        </div>

        <div class="step-actions">
          <button
            class="btn btn-primary"
            :disabled="workflow.jobRunning || analyzing"
            @click="startAnalysis"
          >
            {{ analyzing ? labels.workflow.running : '使用全部素材并分析' }}
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
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import { useWorkflowStore } from '../../stores/workflow.js'
import { useToastStore } from '../../stores/toast.js'
import { useLibraryStore } from '../../stores/library.js'
import labels from '../../i18n/labels.js'

const router = useRouter()
const appStore = useAppStore()
const workflow = useWorkflowStore()
const toast = useToastStore()
const library = useLibraryStore()

const analyzing = ref(false)
const statsLoading = ref(true)
const libStats = computed(() => library.stats)

onMounted(async () => {
  statsLoading.value = true
  await library.loadStats()
  statsLoading.value = false
})

async function startAnalysis() {
  if (!appStore.ready) {
    toast.show(
      '请先创建或打开一个项目，然后再开始分析素材',
      'warn',
      6000,
      { label: '创建项目', handler: () => router.push('/create/project') }
    )
    return
  }
  analyzing.value = true
  try {
    await workflow.runStep(1)
  } finally {
    analyzing.value = false
  }
}

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

/* Material source panel */
.material-source {
  margin-bottom: 16px;
}

.source-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  background: var(--surface1, var(--bg2, #1e1e1e));
}

.source-header {
  margin-bottom: 4px;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 32px 16px;
}
.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}
.empty-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

/* Skeleton loading */
.skeleton {
  animation: pulse 1.5s ease-in-out infinite;
}
.skeleton-line {
  height: 14px;
  background: var(--surface2, rgba(128,128,128,0.15));
  border-radius: 4px;
  margin-bottom: 8px;
}
.w60 { width: 60%; }
.w40 { width: 40%; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
