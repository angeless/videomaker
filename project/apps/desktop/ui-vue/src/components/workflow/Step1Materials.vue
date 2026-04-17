<template>
  <div class="step-panel">
    <h3>{{ labels.workflow.steps[0] }}</h3>

    <!-- 已完成状态 -->
    <div v-if="stepDone" class="step-done-banner">
      <span>素材分析已完成
        <span v-if="workflow.selectedAssets.length > 0">— {{ workflow.selectedAssets.length }} 个素材已就绪</span>
      </span>
      <button class="btn btn-sm btn-next" @click="router.push('/create/workflow/2')">继续下一步 →</button>
    </div>

    <!-- 未完成：素材准备面板 -->
    <div v-if="!stepDone" class="material-source">

      <div v-if="statsLoading" class="source-card skeleton">
        <div class="skeleton-line w60"></div>
        <div class="skeleton-line w40"></div>
      </div>

      <template v-else>
        <!-- 模式切换标签 -->
        <div class="source-tabs">
          <button
            class="tab-btn"
            :class="{ active: sourceMode === 'library' }"
            @click="sourceMode = 'library'"
            :disabled="libStats.video_assets === 0"
          >
            素材库选择
            <span v-if="libStats.video_assets > 0" class="tab-count">{{ libStats.video_assets }}</span>
          </button>
          <button
            class="tab-btn"
            :class="{ active: sourceMode === 'import' }"
            @click="sourceMode = 'import'"
          >
            导入新素材
          </button>
        </div>

        <!-- 模式 A：从素材库选择 -->
        <div v-if="sourceMode === 'library'" class="source-card">
          <div v-if="libStats.video_assets === 0" class="empty-state">
            <div class="empty-icon">📂</div>
            <p class="empty-title">素材库暂无视频</p>
            <p class="text-muted">切换到「导入新素材」标签，选择本地文件夹导入</p>
          </div>

          <template v-else>
            <p class="text-muted" style="margin-bottom: 12px">
              勾选要用于本次制作的视频素材（最多 {{ maxSelect }} 个），然后点击「开始制作」。
            </p>

            <div class="picker-search">
              <input
                v-model="pickerQuery"
                class="form-input"
                placeholder="搜索素材..."
                @keyup.enter="searchAssets"
              />
              <button class="btn btn-ghost btn-sm" @click="searchAssets">搜索</button>
              <button
                v-if="pickerSelected.length > 0"
                class="btn btn-ghost btn-sm"
                @click="pickerSelected = []"
              >清空选择</button>
            </div>

            <div v-if="pickerLoading" class="picker-loading">
              <div class="ai-spinner">加载素材中…</div>
            </div>
            <div v-else-if="pickerAssets.length === 0" class="picker-empty text-muted">
              未找到视频素材
            </div>
            <div v-else class="picker-grid">
              <div
                v-for="asset in pickerAssets"
                :key="asset.uid"
                class="picker-item"
                :class="{ selected: pickerSelected.includes(asset.uid) }"
                @click="toggleSelect(asset.uid)"
              >
                <div class="picker-thumb">
                  <img v-if="asset.thumbnail_url" :src="asset.thumbnail_url" :alt="asset.filename" loading="lazy" />
                  <span v-else class="thumb-placeholder">🎬</span>
                  <span v-if="asset.duration" class="picker-duration">{{ formatSec(asset.duration) }}</span>
                  <span class="picker-check" :class="{ checked: pickerSelected.includes(asset.uid) }">
                    {{ pickerSelected.includes(asset.uid) ? '✓' : '' }}
                  </span>
                </div>
                <div class="picker-name" :title="asset.filename">{{ asset.filename }}</div>
              </div>
            </div>

            <div class="picker-footer">
              <span v-if="pickerSelected.length > 0" class="badge badge-info">
                已选 {{ pickerSelected.length }} 个素材
              </span>
              <span v-else class="text-muted">请点击素材卡片进行选择</span>
              <div class="step-actions">
                <button
                  class="btn btn-primary"
                  :disabled="creating || pickerSelected.length === 0"
                  @click="createFromLibrary"
                >
                  {{ creating ? '创建中…' : '开始制作' }}
                </button>
              </div>
            </div>
          </template>
        </div>

        <!-- 模式 B：导入新素材 -->
        <div
          v-if="sourceMode === 'import'"
          class="source-card"
          :class="{ 'drop-active': dragOver }"
          @dragenter.prevent="onDragEnter"
          @dragover.prevent="onDragOver"
          @dragleave.prevent="onDragLeave"
          @drop.prevent="onDrop"
        >
          <!-- 拖拽覆盖层 -->
          <div v-if="dragOver && !importing" class="drop-overlay">
            <div class="drop-overlay-text">松开以选择视频文件</div>
          </div>

          <p class="text-muted" style="margin-bottom: 12px">
            选择本地视频文件或文件夹，或将文件拖拽到此区域。
          </p>

          <!-- 已选路径显示 -->
          <div v-if="importPath && !importing" class="import-selected">
            <div class="import-path-row">
              <span class="import-path">{{ importPath }}</span>
              <span v-if="selectedFileCount > 0" class="text-muted import-file-count">
                （{{ selectedFileCount }} 个视频文件）
              </span>
              <button class="btn btn-ghost btn-xs" @click="clearImport">清除</button>
            </div>
          </div>

          <!-- 导入进度 -->
          <div v-if="importing" class="import-progress">
            <div class="ai-spinner">
              {{ importStatus || '正在处理…' }}
            </div>
            <div class="progress-bar" style="margin-top: 8px">
              <div class="progress-bar-fill" :style="{ width: importProgress + '%' }"></div>
            </div>
          </div>

          <!-- 按钮区域 -->
          <div class="import-actions">
            <button class="btn btn-ghost" @click="pickImportFolder" :disabled="importing">
              选择文件夹
            </button>
            <button class="btn btn-ghost" @click="pickVideoFiles" :disabled="importing">
              选择视频文件
            </button>
            <button
              class="btn btn-primary"
              :disabled="(!importPath && selectedFiles.length === 0) || importing"
              @click="importAndCreate"
            >
              {{ importing ? '导入中…' : '开始制作' }}
            </button>
          </div>
        </div>
      </template>
    </div>

    <!-- 已有项目但 Step 1 未完成 -->
    <div v-if="!stepDone && appStore.ready" class="step-actions" style="margin-top: 8px">
      <button
        class="btn btn-ghost"
        :disabled="workflow.jobRunning"
        @click="reanalyze"
      >
        重新分析当前项目素材
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import { useWorkflowStore } from '../../stores/workflow.js'
import { useToastStore } from '../../stores/toast.js'
import { useLibraryStore } from '../../stores/library.js'
import { useApiStore } from '../../stores/api.js'
import { useProjectStore } from '../../stores/project.js'
import labels from '../../i18n/labels.js'

const router = useRouter()
const appStore = useAppStore()
const workflow = useWorkflowStore()
const toast = useToastStore()
const library = useLibraryStore()
const apiStore = useApiStore()
const projectStore = useProjectStore()

// ── 状态 ──
const statsLoading = ref(true)
const libStats = computed(() => library.stats)
const sourceMode = ref('library')
const maxSelect = 50

// ── 素材库选择 ──
const pickerQuery = ref('')
const pickerAssets = ref([])
const pickerLoading = ref(false)
const pickerSelected = ref([])

// ── 导入模式 ──
const importPath = ref('')
const selectedFiles = ref([])  // 选中的具体文件路径
const importing = ref(false)
const importProgress = ref(0)
const importStatus = ref('')
const dragOver = ref(false)
let dragEnterCount = 0  // track nested dragenter/dragleave

const selectedFileCount = computed(() => selectedFiles.value.length)
const creating = ref(false)

// ── 初始化 ──
onMounted(async () => {
  statsLoading.value = true
  await library.loadStats()
  statsLoading.value = false

  if (library.stats.video_assets > 0) {
    await searchAssets()
  } else {
    sourceMode.value = 'import'
  }
})

// Round-14: cancel any in-flight poll chains on unmount.
onBeforeUnmount(() => {
  _pollAlive = false
  if (_pollTimer) {
    clearTimeout(_pollTimer)
    _pollTimer = null
  }
})

const stepDone = computed(() => {
  const s = (appStore.steps || []).find(s => s.n === 1)
  return s ? s.status === 'done' : false
})

// ── 素材搜索 ──
async function searchAssets() {
  pickerLoading.value = true
  const params = new URLSearchParams({
    q: pickerQuery.value,
    mode: 'hybrid',
    media_type: 'video',
    limit: '120',
    offset: '0',
  })
  const data = await apiStore.api('GET', `/api/library/search?${params}`)
  pickerLoading.value = false
  if (data.error) {
    toast.show(data.error, 'danger')
    return
  }
  pickerAssets.value = data.results || []
}

function toggleSelect(uid) {
  const idx = pickerSelected.value.indexOf(uid)
  if (idx >= 0) {
    pickerSelected.value.splice(idx, 1)
  } else {
    if (pickerSelected.value.length >= maxSelect) {
      toast.show(`最多选择 ${maxSelect} 个素材`, 'warn')
      return
    }
    pickerSelected.value.push(uid)
  }
}

// ── 从素材库创建项目 ──
async function createFromLibrary() {
  if (pickerSelected.value.length === 0) return
  creating.value = true
  const data = await apiStore.api('POST', '/api/init', {
    selected_video_uids: pickerSelected.value,
  })
  creating.value = false
  if (data.error) {
    toast.show(data.error, 'danger')
    return
  }
  toast.show(`项目已创建，${data.selected_count || pickerSelected.value.length} 个素材就绪`, 'success')
  await projectStore.fetchStatus()
  await workflow.loadStepData()
  router.push('/create/workflow/2')
}

// ── 选择文件夹 ──
async function pickImportFolder() {
  const path = await projectStore.pickFolder()
  if (path) {
    importPath.value = path
    selectedFiles.value = []
  }
}

// ── 选择视频文件（多选）──
async function pickVideoFiles() {
  const data = await apiStore.api('POST', '/api/dialog/files')
  if (data.cancelled) return
  if (data.error) {
    toast.show(data.error, 'danger')
    return
  }
  const paths = data.paths || []
  if (paths.length === 0) return

  selectedFiles.value = paths
  // 显示路径用第一个文件的目录
  const parts = paths[0].replace(/\\/g, '/').split('/')
  parts.pop()
  importPath.value = parts.join('/')
  toast.show(`已选择 ${paths.length} 个视频文件`, 'success')
}

// ── 拖拽处理 ──
function onDragEnter(e) {
  dragEnterCount++
  if (e.dataTransfer?.types?.includes('Files')) dragOver.value = true
}
function onDragOver(e) {
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
}
function onDragLeave() {
  dragEnterCount--
  if (dragEnterCount <= 0) {
    dragEnterCount = 0
    dragOver.value = false
  }
}
function onDrop(e) {
  dragOver.value = false
  dragEnterCount = 0
  if (importing.value) return

  // pywebview WKWebView doesn't expose file paths in drop events.
  // Auto-open the native file picker so the user gets valid paths.
  const fileCount = e.dataTransfer?.files?.length || 0
  if (fileCount > 0) {
    toast.show(`检测到 ${fileCount} 个文件，正在打开文件选择器…`, 'info')
    pickVideoFiles()
  }
}

function clearImport() {
  importPath.value = ''
  selectedFiles.value = []
}

// ── 导入并创建项目 ──
async function importAndCreate() {
  if (!importPath.value && selectedFiles.value.length === 0) return
  importing.value = true
  importProgress.value = 0

  // 模式 A：选了具体文件 → 直接传文件路径创建项目
  if (selectedFiles.value.length > 0) {
    importStatus.value = '正在创建项目…'
    const initData = await apiStore.api('POST', '/api/init', {
      selected_video_paths: selectedFiles.value,
    })
    if (initData.error) {
      importing.value = false
      toast.show(initData.error, 'danger')
      return
    }
    toast.show(`项目已创建，${initData.selected_count || selectedFiles.value.length} 个视频`, 'success')
    await projectStore.fetchStatus()
    await workflow.loadStepData()

    if (initData.needs_analysis || appStore.currentStep <= 1) {
      importStatus.value = '正在分析素材（大文件可能需要较长时间）…'
      importProgress.value = 10
      await workflow.runStep(1)
      await waitForWorkflowJob()
      // Step 1 完成后自动审核通过，推进到 Step 2
      importStatus.value = '分析完成，正在确认…'
      await workflow.approveStep(1)
    }
    importing.value = false
    await projectStore.fetchStatus()
    await workflow.loadStepData()
    if (stepDone.value || appStore.currentStep > 1) {
      router.push('/create/workflow/2')
    }
    return
  }

  // 模式 B：选了文件夹 → 入库 + 创建项目
  importStatus.value = '正在扫描文件夹…'
  const ingestData = await apiStore.api('POST', '/api/library/ingest/local/start', {
    path: importPath.value,
    max_videos: 200,
  })
  if (ingestData.error) {
    importing.value = false
    toast.show(ingestData.error, 'danger')
    return
  }

  const jobId = ingestData.job_id
  if (jobId) {
    await pollUntilDone(jobId)
  }

  importStatus.value = '入库完成，正在创建项目…'
  await library.loadStats()

  const initData = await apiStore.api('POST', '/api/init', {
    videos_dir: importPath.value,
  })

  if (initData.error) {
    importing.value = false
    toast.show(initData.error, 'danger')
    return
  }

  toast.show('项目已创建，开始分析素材', 'success')
  await projectStore.fetchStatus()
  await workflow.loadStepData()

  if (appStore.currentStep <= 1) {
    importStatus.value = '正在分析素材（大文件可能需要较长时间）…'
    importProgress.value = 10
    await workflow.runStep(1)
    await waitForWorkflowJob()
    importStatus.value = '分析完成，正在确认…'
    await workflow.approveStep(1)
  }
  importing.value = false
  await projectStore.fetchStatus()
  await workflow.loadStepData()
  if (stepDone.value || appStore.currentStep > 1) {
    router.push('/create/workflow/2')
  }
}

// ── 轮询 Job ──
async function pollUntilDone(jobId) {
  return new Promise((resolve) => {
    async function poll() {
      const data = await apiStore.api('GET', `/api/job/${jobId}`)
      if (data.error) { resolve(); return }

      importProgress.value = data.progress || 0

      // 读取进度文本（后端通过 log 或 ingest_meta 传递）
      const logs = data.log || []
      if (logs.length > 0) {
        const last = logs[logs.length - 1]
        importStatus.value = typeof last === 'string' ? last : (last.message || importStatus.value)
      }
      if (data.ingest_meta?.current_file) {
        importStatus.value = `正在处理: ${data.ingest_meta.current_file}`
      }

      const status = `${data.status || ''}`.toLowerCase()
      if (status === 'completed' || status === 'done' || status === 'error' || status === 'failed') {
        resolve()
        return
      }
      if (!_pollAlive) { resolve(); return }
      _pollTimer = setTimeout(poll, 1500)
    }
    poll()
  })
}

// Round-14: track poll timers so navigation away from step 1 doesn't
// leave setTimeout chains hitting /api/workflow/* forever.
let _pollTimer = null
let _pollAlive = true

// ── 等待 workflow job 完成 ──
function waitForWorkflowJob() {
  return new Promise((resolve) => {
    let ticks = 0
    function check() {
      ticks++
      if (!_pollAlive) { resolve(); return }
      // Sync progress display with workflow store
      if (workflow.jobStatus) {
        importStatus.value = `正在分析素材… ${workflow.jobStatus}`
      }
      importProgress.value = Math.min(90, 10 + ticks * 2)

      if (!workflow.jobRunning) {
        importProgress.value = 100
        resolve()
        return
      }
      _pollTimer = setTimeout(check, 1000)
    }
    // Give the poll a moment to start
    _pollTimer = setTimeout(check, 500)
  })
}

// ── 重新分析 ──
async function reanalyze() {
  await workflow.runStep(1)
}

function formatSec(sec) {
  if (!sec) return ''
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`
}
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

.source-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.2s;
}
.tab-btn:hover:not(:disabled) { color: var(--text); }
.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 500;
}
.tab-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.tab-count {
  background: var(--accent);
  color: #fff;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  margin-left: 4px;
}

.material-source { margin-bottom: 16px; }
.source-card {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  background: var(--surface1, var(--bg2, #1e1e1e));
  transition: border-color 0.2s, box-shadow 0.2s;
}

.empty-state { text-align: center; padding: 32px 16px; }
.empty-icon { font-size: 32px; margin-bottom: 8px; }
.empty-title { font-size: 15px; font-weight: 600; margin-bottom: 4px; }

.picker-search { display: flex; gap: 8px; margin-bottom: 12px; }
.picker-search .form-input { flex: 1; }
.picker-loading, .picker-empty { padding: 24px; text-align: center; }
.picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding: 4px;
}
.picker-item {
  border: 2px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
  overflow: hidden;
  background: var(--surface2, rgba(128,128,128,0.08));
  user-select: none;
}
.picker-item:hover { border-color: var(--border-hover, rgba(128,128,128,0.3)); }
.picker-item.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}
.picker-thumb {
  position: relative;
  aspect-ratio: 16/9;
  background: #000;
  overflow: hidden;
}
.picker-thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%; height: 100%;
  font-size: 24px;
  background: var(--surface2, #2a2a2a);
}
.picker-duration {
  position: absolute;
  bottom: 4px; right: 4px;
  background: rgba(0,0,0,0.7);
  color: #fff; font-size: 10px;
  padding: 1px 5px; border-radius: 3px;
}
.picker-check {
  position: absolute;
  top: 4px; left: 4px;
  width: 20px; height: 20px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.5);
  background: rgba(0,0,0,0.3);
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 12px; font-weight: bold;
  transition: all 0.15s;
}
.picker-check.checked { background: var(--accent); border-color: var(--accent); }
.picker-name {
  padding: 4px 6px;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}
.picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

/* Drop zone */
.source-card.drop-active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
}
.drop-overlay {
  position: absolute;
  inset: 0;
  background: rgba(99, 102, 241, 0.08);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  pointer-events: none;
}
.drop-overlay-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--accent);
}

/* Import mode */
.import-selected {
  background: var(--surface2, rgba(128,128,128,0.08));
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.import-path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.import-path {
  font-family: monospace;
  font-size: 12px;
  color: var(--accent);
  word-break: break-all;
}
.import-file-count { font-size: 12px; }
.import-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.import-progress {
  padding: 12px;
  background: var(--surface2, rgba(128,128,128,0.08));
  border-radius: 6px;
  margin-bottom: 12px;
}

.skeleton { animation: pulse 1.5s ease-in-out infinite; }
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
