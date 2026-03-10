<script setup>
import { ref, computed, watch } from 'vue'
import { useLibraryStore } from '../../stores/library'

const emit = defineEmits(['search-library'])

const store = useLibraryStore()
const expanded = ref(false)
const showApplyDetail = ref(false)
const compareJobA = ref(null)
const compareJobB = ref(null)
const showExportMenu = ref(false)

// ── D-2: Manual binding state ──
const showCandidatesForItem = ref(null)   // item_id currently showing candidates
const candidateLoading = ref(false)
const candidateList = ref([])

// ── D-3: Workbench / batch / history / outputs ──
const workbenchTab = ref('actionable')  // 'actionable' | 'resolved' | 'all'
const batchMode = ref(false)
const showItemHistoryId = ref(null)     // item_id showing history drawer
const showOutputs = ref(false)
const showDiffDetail = ref(false)       // toggle diff_items in confirm panel

// ── D-4: Long-term sync + handover ──
const showJobChain = ref(false)
const showHandover = ref(false)

// ── Auto-load history when panel expands ──
watch(expanded, (val) => {
  if (val) {
    const p = store.projectRelinkProjectPath.trim()
    store.fetchProjectRelinkHistory(p || undefined)
  }
})

const hasRelinkedItems = computed(() => {
  const items = store.projectRelinkJob?.items || store.projectRelinkJob?.summary ? (store.projectRelinkJob.items || []) : []
  return items.some(i => i.status === 'relinked')
})

const hasMissingItems = computed(() => {
  return items.value.some(i => i.status === 'missing' || i.status === 'unmatched')
})

const summary = computed(() => {
  const job = store.projectRelinkJob
  if (!job) return null
  return job.summary || {
    total_refs: job.total_refs || 0,
    stable_refs: job.stable_refs || 0,
    changed_refs: job.changed_refs || 0,
    missing_refs: job.missing_refs || 0,
    unmatched_refs: job.unmatched_refs || 0,
  }
})

const items = computed(() => {
  return store.projectRelinkJob?.items || []
})

const jobId = computed(() => {
  return store.projectRelinkJob?.job_id || null
})

// ── C-2: Filter ──
const filters = computed(() => [
  { key: 'all', label: '全部', count: items.value.length },
  { key: 'relinked', label: '已恢复', count: items.value.filter(i => i.status === 'relinked').length },
  { key: 'missing', label: '缺失', count: items.value.filter(i => i.status === 'missing').length },
  { key: 'unmatched', label: '未匹配', count: items.value.filter(i => i.status === 'unmatched').length },
])

const filteredItems = computed(() => {
  if (store.projectRelinkFilter === 'all') return items.value
  return items.value.filter(i => i.status === store.projectRelinkFilter)
})

// ── D-1: Preview apply computed ──
const previewApply = computed(() => store.projectRelinkPreviewApply)

// ── D-3: Workbench data ──
const workbench = computed(() => store.projectRelinkWorkbench)

// ── D-3: Workbench-based items grouping ──
const workbenchGroups = computed(() => {
  if (!workbench.value) return null
  return {
    missing: workbench.value.missing || [],
    unmatched: workbench.value.unmatched || [],
    relinked_manual: workbench.value.relinked_manual || [],
    relinked_system: workbench.value.relinked_system || [],
    stable: workbench.value.stable || [],
  }
})

// D-3: Filtered items based on workbench tab
const workbenchFilteredItems = computed(() => {
  if (!workbenchGroups.value) return filteredItems.value
  const g = workbenchGroups.value
  if (workbenchTab.value === 'actionable') return [...g.missing, ...g.unmatched]
  if (workbenchTab.value === 'resolved') return [...g.relinked_manual, ...g.relinked_system, ...g.stable]
  return [...g.missing, ...g.unmatched, ...g.relinked_manual, ...g.relinked_system, ...g.stable]
})

// D-3: Workbench tab counts
const workbenchCounts = computed(() => {
  if (!workbenchGroups.value) return { actionable: 0, resolved: 0, all: 0 }
  const g = workbenchGroups.value
  return {
    actionable: g.missing.length + g.unmatched.length,
    resolved: g.relinked_manual.length + g.relinked_system.length + g.stable.length,
    all: g.missing.length + g.unmatched.length + g.relinked_manual.length + g.relinked_system.length + g.stable.length,
  }
})

// D-3: Batch selection
const selectedItemIds = computed(() => store.pendingBindItemIds || [])

// D-3: Can batch bind (must have selected items)
const canBatchBind = computed(() => selectedItemIds.value.length > 0)

// D-3: Item history
const itemHistory = computed(() => store.projectRelinkItemHistory || [])

// D-3: Outputs
const outputs = computed(() => store.projectRelinkOutputs || [])

// D-3: Diff items from preview
const diffItems = computed(() => {
  if (!previewApply.value) return []
  return previewApply.value.diff_items || []
})

// D-3: Preview summary
const previewSummary = computed(() => {
  if (!previewApply.value) return null
  return previewApply.value.summary || null
})

// ── Actions ──
async function doAnalyze() {
  const p = store.projectRelinkProjectPath.trim()
  if (!p) return

  // Pre-validate (non-blocking)
  const v = await store.validateProjectRelink(p)
  if (v && !v.valid && v.errors && v.errors.length) {
    // Show warning but continue
  }

  await store.runProjectRelink(p)
  // Refresh history after analysis
  store.fetchProjectRelinkHistory(p)
  // D-3: Auto-load workbench
  if (jobId.value) doFetchWorkbench()
}

function doExport() {
  if (!jobId.value) return
  store.exportProjectRelink(jobId.value)
}

function doCopy() {
  const data = { summary: summary.value, items: items.value }
  navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    .then(() => {})
    .catch(() => {})
}

// D-1: "生成修复副本" now triggers preview first
function doPreviewApply() {
  if (!jobId.value) return
  showApplyDetail.value = false
  store.previewProjectRelinkApply(jobId.value)
}

function doCompare() {
  if (!compareJobA.value || !compareJobB.value) return
  store.compareProjectRelinkJobs(compareJobA.value, compareJobB.value)
}

function doSearchLibrary(assetName) {
  emit('search-library', assetName)
}

// ── D-2: Manual binding actions ──
async function doShowCandidates(item) {
  if (showCandidatesForItem.value === item.item_id) {
    showCandidatesForItem.value = null
    candidateList.value = []
    return
  }
  showCandidatesForItem.value = item.item_id
  candidateLoading.value = true
  candidateList.value = []
  try {
    // fetchCandidateSuggestions loads into store.projectRelinkSuggestions
    await store.fetchCandidateSuggestions(jobId.value)
    // Find candidates for this specific item
    const match = (store.projectRelinkSuggestions || []).find(s => s.item_id === item.item_id)
    candidateList.value = match ? match.candidates || [] : []
  } catch { candidateList.value = [] }
  candidateLoading.value = false
}

async function doBindCandidate(itemId, candidateUid) {
  await store.bindProjectRelinkItem(itemId, candidateUid, 'candidate')
  showCandidatesForItem.value = null
  candidateList.value = []
}

async function doUnbind(itemId) {
  await store.unbindProjectRelinkItem(itemId)
}

async function doRefreshPaths() {
  if (!jobId.value) return
  await store.refreshProjectRelinkItems(jobId.value)
}

function doSearchBind(item) {
  store.setPendingBind(item.item_id)
  emit('search-library', item.asset_name)
}

// ── D-3: Workbench + batch + history + outputs actions ──
async function doFetchWorkbench() {
  if (!jobId.value) return
  await store.fetchProjectRelinkWorkbench(jobId.value)
}

function doToggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) store.clearPendingBindItems()
}

function doToggleSelectItem(itemId) {
  store.togglePendingBindItem(itemId)
}

async function doBatchBind(uid, decisionSource = 'candidate') {
  if (!canBatchBind.value) return
  const bindings = selectedItemIds.value.map(id => ({ item_id: id, uid }))
  await store.batchBindProjectRelinkItems(bindings, decisionSource)
  batchMode.value = false
  store.clearPendingBindItems()
  doFetchWorkbench()
}

async function doShowItemHistory(itemId) {
  if (showItemHistoryId.value === itemId) {
    showItemHistoryId.value = null
    return
  }
  showItemHistoryId.value = itemId
  await store.fetchProjectRelinkItemHistory(itemId)
}

async function doUndoBind(itemId) {
  await store.undoProjectRelinkItemBind(itemId)
  // Refresh history if open
  if (showItemHistoryId.value === itemId) {
    await store.fetchProjectRelinkItemHistory(itemId)
  }
  doFetchWorkbench()
}

async function doFetchOutputs() {
  if (!jobId.value) return
  showOutputs.value = !showOutputs.value
  if (showOutputs.value) {
    await store.fetchProjectRelinkOutputs(jobId.value)
  }
}

// ── D-4: Sync + handover actions ──
async function doReanalyze() {
  const p = store.projectRelinkProjectPath.trim()
  if (!p) return
  await store.reanalyzeProjectRelink(p)
  if (jobId.value) doFetchWorkbench()
}

async function doToggleJobChain() {
  showJobChain.value = !showJobChain.value
  if (showJobChain.value) {
    const p = store.projectRelinkProjectPath.trim()
    if (p) await store.fetchProjectRelinkJobChain(p)
  }
}

async function doVerify() {
  if (!jobId.value) return
  await store.verifyProjectRelinkState(jobId.value)
}

async function doGenerateHandover() {
  if (!jobId.value) return
  await store.generateHandoverReport(jobId.value)
}

function doExportHandover(fmt) {
  if (!jobId.value) return
  store.exportHandoverReport(jobId.value, fmt)
}

function doLoadJob(jid) {
  store.fetchProjectRelinkJob(jid)
  if (jid) store.fetchProjectRelinkWorkbench(jid)
}

// D-4: Verify health label (independent from status)
function verifyHealthLabel(item) {
  if (!item.verified_at) return '未验证'
  // Re-check using the verification result if available
  const v = store.projectRelinkVerification
  if (v && v.stale_items) {
    const stale = v.stale_items.find(s => s.item_id === item.item_id)
    if (stale) return '已失效'
  }
  return '有效'
}

function verifyHealthClass(item) {
  if (!item.verified_at) return 'prp-health-unchecked'
  const v = store.projectRelinkVerification
  if (v && v.stale_items) {
    const stale = v.stale_items.find(s => s.item_id === item.item_id)
    if (stale) return 'prp-health-stale'
  }
  return 'prp-health-valid'
}

function bindingModeLabel(mode) {
  return { manual: '人工', system: '系统', none: '-' }[mode] || mode || '-'
}

function actionLabel(action) {
  return { apply: '修复', skip: '跳过' }[action] || action || ''
}

function statusLabel(s) {
  return { stable: '正常', relinked: '已恢复', missing: '缺失', unmatched: '未匹配' }[s] || s
}

function jobStatusBadge(s) {
  return { done: '完成', failed: '失败', running: '运行中', pending: '排队中' }[s] || s
}

function matchLabel(type) {
  return { path: '路径匹配', filename: '文件名匹配' }[type] || ''
}

function confidenceLabel(val) {
  if (val == null) return ''
  const pct = Math.round(val * 100)
  return `${pct}%`
}

function confidenceClass(val) {
  if (val == null) return ''
  if (val >= 0.9) return 'prp-conf-high'
  if (val >= 0.6) return 'prp-conf-mid'
  return 'prp-conf-low'
}

function truncPath(p) {
  if (!p) return ''
  return p.length > 60 ? '...' + p.slice(-57) : p
}

function formatTime(ts) {
  if (!ts) return ''
  return ts.replace('T', ' ').slice(0, 16)
}
</script>

<template>
  <div class="prp-panel">
    <div class="prp-header" @click="expanded = !expanded">
      <span class="prp-chevron">{{ expanded ? '▾' : '▸' }}</span>
      <span class="prp-title">工程素材 Relink</span>
      <span v-if="summary && summary.changed_refs" class="badge badge-accent" style="margin-left:6px">
        {{ summary.changed_refs }} 可恢复
      </span>
      <!-- D-2: Pending bind indicator -->
      <span v-if="store.pendingBindItemId" class="prp-pending-bind-badge">绑定中...</span>
    </div>

    <div v-if="expanded" class="prp-body">
      <!-- Validation warning -->
      <div v-if="store.projectRelinkValidation && !store.projectRelinkValidation.valid" class="prp-validation-warn">
        ⚠️ {{ (store.projectRelinkValidation.errors || []).join('; ') }}
      </div>

      <!-- Input -->
      <div class="prp-input-row">
        <input
          type="text"
          class="form-input"
          v-model="store.projectRelinkProjectPath"
          placeholder="剪映工程文件路径（JSON）"
          @keyup.enter="doAnalyze"
        />
        <button
          class="btn btn-primary btn-sm"
          :disabled="store.projectRelinkLoading || !store.projectRelinkProjectPath.trim()"
          @click="doAnalyze"
        >
          {{ store.projectRelinkLoading ? '分析中...' : '分析' }}
        </button>
      </div>

      <!-- Summary -->
      <div v-if="summary" class="prp-summary">
        <div class="prp-stat-card">
          <div class="prp-stat-num">{{ summary.total_refs }}</div>
          <div class="prp-stat-label">总引用</div>
        </div>
        <div class="prp-stat-card prp-stat-stable">
          <div class="prp-stat-num">{{ summary.stable_refs }}</div>
          <div class="prp-stat-label">正常</div>
        </div>
        <div class="prp-stat-card prp-stat-relinked">
          <div class="prp-stat-num">{{ summary.changed_refs }}</div>
          <div class="prp-stat-label">已恢复</div>
        </div>
        <div class="prp-stat-card prp-stat-missing">
          <div class="prp-stat-num">{{ summary.missing_refs }}</div>
          <div class="prp-stat-label">缺失</div>
        </div>
        <div class="prp-stat-card prp-stat-unmatched">
          <div class="prp-stat-num">{{ summary.unmatched_refs }}</div>
          <div class="prp-stat-label">未匹配</div>
        </div>
      </div>

      <!-- D-4: Predecessor info bar -->
      <div v-if="store.projectRelinkJob && store.projectRelinkJob.predecessor_job_id" class="prp-predecessor-bar">
        <span class="prp-pred-label">继承自</span>
        <span class="prp-pred-link" @click="doLoadJob(store.projectRelinkJob.predecessor_job_id)">#{{ store.projectRelinkJob.predecessor_job_id }}</span>
        <span v-if="store.projectRelinkJob.inherited_bindings" class="prp-pred-count">{{ store.projectRelinkJob.inherited_bindings }} 个绑定</span>
        <span v-if="store.projectRelinkJob.handover_at" class="badge badge-success prp-handover-badge">已交接</span>
      </div>

      <!-- D-3: Workbench tabs (replaces simple filter when workbench loaded) -->
      <div v-if="workbenchGroups && items.length" class="prp-workbench-tabs">
        <button class="prp-wb-tab" :class="{ active: workbenchTab === 'actionable' }"
          @click="workbenchTab = 'actionable'">
          待处理 <span class="prp-wb-count">({{ workbenchCounts.actionable }})</span>
        </button>
        <button class="prp-wb-tab" :class="{ active: workbenchTab === 'resolved' }"
          @click="workbenchTab = 'resolved'">
          已解决 <span class="prp-wb-count">({{ workbenchCounts.resolved }})</span>
        </button>
        <button class="prp-wb-tab" :class="{ active: workbenchTab === 'all' }"
          @click="workbenchTab = 'all'">
          全部 <span class="prp-wb-count">({{ workbenchCounts.all }})</span>
        </button>
        <span class="prp-wb-spacer"></span>
        <!-- D-3: Batch mode toggle -->
        <button v-if="workbenchTab === 'actionable' && workbenchCounts.actionable > 0"
          class="btn btn-xs prp-batch-toggle"
          :class="{ 'prp-batch-active': batchMode }"
          @click="doToggleBatchMode">
          {{ batchMode ? '退出批量' : '批量选择' }}
        </button>
      </div>

      <!-- Fallback: D-1 filter bar when workbench not loaded -->
      <div v-else-if="items.length" class="prp-filter-bar">
        <button v-for="f in filters" :key="f.key"
          class="prp-filter-btn" :class="{ active: store.projectRelinkFilter === f.key }"
          @click="store.projectRelinkFilter = f.key"
        >{{ f.label }} <span v-if="f.count" class="prp-filter-count">({{ f.count }})</span>
        </button>
      </div>

      <!-- D-3: Batch bind action bar (visible in batch mode with selections) -->
      <div v-if="batchMode && selectedItemIds.length" class="prp-batch-bar">
        <span class="prp-batch-info">已选 {{ selectedItemIds.length }} 项</span>
        <button class="btn btn-xs" @click="store.clearPendingBindItems()">清除选择</button>
      </div>

      <!-- Items (use workbench items when available, otherwise fallback) -->
      <div v-if="(workbenchGroups ? workbenchFilteredItems : filteredItems).length" class="prp-items-list">
        <div v-for="(item, idx) in (workbenchGroups ? workbenchFilteredItems : filteredItems)" :key="item.item_id || idx" class="prp-item">
          <!-- D-3: Batch checkbox -->
          <input v-if="batchMode && (item.status === 'missing' || item.status === 'unmatched')"
            type="checkbox"
            class="prp-batch-check"
            :checked="selectedItemIds.includes(item.item_id)"
            @change="doToggleSelectItem(item.item_id)"
          />

          <span class="prp-status-badge" :class="'prp-s-' + item.status">
            {{ statusLabel(item.status) }}
          </span>
          <span class="prp-item-name">{{ item.asset_name }}</span>
          <span v-if="item.media_type" class="prp-media-type">{{ item.media_type }}</span>
          <span
            v-if="item.fingerprint_match_type && item.fingerprint_match_type !== 'none'"
            class="prp-match-tag"
            :title="item.reason || ''"
          >{{ matchLabel(item.fingerprint_match_type) }}</span>
          <span
            v-if="item.match_confidence != null && item.status !== 'stable'"
            class="prp-conf-badge"
            :class="confidenceClass(item.match_confidence)"
          >{{ confidenceLabel(item.match_confidence) }}</span>

          <!-- D-2: Binding mode badge -->
          <span v-if="item.binding_mode === 'manual'" class="prp-bind-badge prp-bind-manual">人工绑定</span>
          <span v-else-if="item.binding_mode === 'system' && (item.status === 'relinked' || item.status === 'stable')" class="prp-bind-badge prp-bind-system">系统匹配</span>
          <!-- D-4: Inherited binding badge -->
          <span v-if="item.inherited_from_item_id" class="prp-bind-badge prp-bind-inherited">继承绑定</span>
          <!-- D-4: Verify health indicator (independent from status per rule #3) -->
          <span v-if="item.verified_at" class="prp-health-badge" :class="verifyHealthClass(item)">{{ verifyHealthLabel(item) }}</span>

          <!-- D-1: Search library button for missing/unmatched -->
          <button
            v-if="item.status === 'missing' || item.status === 'unmatched'"
            class="btn btn-xs prp-search-jump"
            @click="doSearchLibrary(item.asset_name)"
          >搜索素材库</button>

          <!-- D-2: Candidate suggestions button for missing/unmatched -->
          <button
            v-if="item.status === 'missing' || item.status === 'unmatched'"
            class="btn btn-xs prp-candidate-btn"
            @click="doShowCandidates(item)"
          >{{ showCandidatesForItem === item.item_id ? '收起候选' : '查看候选' }}</button>

          <!-- D-2: Search-bind button for missing/unmatched -->
          <button
            v-if="item.status === 'missing' || item.status === 'unmatched'"
            class="btn btn-xs prp-search-bind-btn"
            @click="doSearchBind(item)"
          >搜索绑定</button>

          <!-- D-2: Unbind button for manually bound items -->
          <button
            v-if="item.binding_mode === 'manual'"
            class="btn btn-xs prp-unbind-btn"
            :disabled="store.projectRelinkBindingInProgress"
            @click="doUnbind(item.item_id)"
          >解除绑定</button>

          <!-- D-3: Undo last bind (shortcut for manual items) -->
          <button
            v-if="item.binding_mode === 'manual'"
            class="btn btn-xs prp-undo-btn"
            :disabled="store.projectRelinkBindingInProgress"
            @click="doUndoBind(item.item_id)"
          >撤销绑定</button>

          <!-- D-3: Item history button -->
          <button
            v-if="item.manual_uid || item.binding_mode === 'manual'"
            class="btn btn-xs prp-history-btn"
            @click="doShowItemHistory(item.item_id)"
          >{{ showItemHistoryId === item.item_id ? '收起历史' : '操作历史' }}</button>

          <div class="prp-item-paths">
            <template v-if="item.status === 'stable'">
              <span class="prp-path prp-path-ok">{{ truncPath(item.old_path) }}</span>
            </template>
            <template v-else-if="item.status === 'relinked'">
              <span class="prp-path prp-path-old">{{ truncPath(item.old_path) }}</span>
              <span class="prp-arrow">→</span>
              <span class="prp-path prp-path-new">{{ truncPath(item.effective_new_path || item.new_path) }}</span>
            </template>
            <template v-else-if="item.status === 'missing'">
              <span class="prp-path prp-path-miss">{{ truncPath(item.old_path) }}</span>
              <span class="prp-hint-text">无可用路径</span>
            </template>
            <template v-else>
              <span class="prp-path prp-path-gray">{{ truncPath(item.old_path) }}</span>
              <span class="prp-hint-text">未匹配到素材库</span>
            </template>
          </div>

          <!-- D-2: Candidate suggestions sub-panel -->
          <div v-if="showCandidatesForItem === item.item_id" class="prp-candidates-panel">
            <div v-if="candidateLoading" class="prp-candidates-loading">加载候选中...</div>
            <div v-else-if="!candidateList.length" class="prp-candidates-empty">无候选建议</div>
            <div v-else class="prp-candidates-list">
              <div v-for="c in candidateList" :key="c.uid" class="prp-candidate-row">
                <span class="prp-candidate-name">{{ c.filename }}</span>
                <span class="prp-candidate-score">{{ Math.round((c.similarity || 0) * 100) }}%</span>
                <span v-if="c.available" class="prp-candidate-avail">可用</span>
                <span v-else class="prp-candidate-unavail">不可用</span>
                <button
                  v-if="c.available"
                  class="btn btn-xs prp-candidate-bind-btn"
                  :disabled="store.projectRelinkBindingInProgress"
                  @click="doBindCandidate(item.item_id, c.uid)"
                >绑定</button>
              </div>
            </div>
          </div>

          <!-- D-3: Item history drawer -->
          <div v-if="showItemHistoryId === item.item_id" class="prp-item-history-drawer">
            <div v-if="store.projectRelinkItemHistoryLoading" class="prp-ih-loading">加载历史...</div>
            <div v-else-if="!itemHistory.length" class="prp-ih-empty">无操作记录</div>
            <div v-else class="prp-ih-list">
              <div v-for="h in itemHistory" :key="h.action_id" class="prp-ih-row">
                <span class="prp-ih-type" :class="'prp-ih-' + h.action_type">{{ h.action_type }}</span>
                <span class="prp-ih-time">{{ formatTime(h.created_at) }}</span>
                <span v-if="h.payload_json" class="prp-ih-detail">{{ h.payload_json }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="store.projectRelinkJob && !store.projectRelinkLoading && !items.length" class="prp-empty">
        工程中没有素材引用
      </div>
      <div v-else-if="items.length && !filteredItems.length" class="prp-empty">
        当前筛选无结果
      </div>

      <!-- Actions -->
      <div v-if="summary" class="prp-actions">
        <button class="btn btn-sm" @click="doCopy">复制 JSON</button>
        <button class="btn btn-sm" @click="doExport">导出 JSON</button>

        <!-- D-2: Refresh paths button -->
        <button
          v-if="items.length"
          class="btn btn-sm"
          :disabled="store.projectRelinkBindingInProgress"
          @click="doRefreshPaths"
        >刷新路径</button>

        <!-- D-3: Workbench refresh -->
        <button
          v-if="jobId"
          class="btn btn-sm"
          :disabled="store.projectRelinkWorkbenchLoading"
          @click="doFetchWorkbench"
        >{{ store.projectRelinkWorkbenchLoading ? '加载中...' : '刷新工作台' }}</button>

        <!-- D-3: Outputs toggle -->
        <button
          v-if="jobId"
          class="btn btn-sm"
          :disabled="store.projectRelinkOutputsLoading"
          @click="doFetchOutputs"
        >{{ showOutputs ? '收起副本记录' : '副本记录' }}</button>

        <!-- D-1: Export missing dropdown -->
        <div v-if="hasMissingItems" class="prp-dropdown-wrap">
          <button class="btn btn-sm" @click="showExportMenu = !showExportMenu">
            缺失清单 ▾
          </button>
          <div v-if="showExportMenu" class="prp-dropdown-menu">
            <div class="prp-dropdown-item" @click="store.copyMissingList(); showExportMenu = false">复制到剪贴板</div>
            <div class="prp-dropdown-item" @click="store.exportMissingItems(jobId, 'json'); showExportMenu = false">导出 JSON</div>
            <div class="prp-dropdown-item" @click="store.exportMissingItems(jobId, 'csv'); showExportMenu = false">导出 CSV</div>
          </div>
        </div>

        <!-- D-4: Reanalyze (carry forward) button -->
        <button
          v-if="jobId && store.projectRelinkJob?.status === 'done'"
          class="btn btn-sm"
          :disabled="store.projectRelinkReanalyzing"
          @click="doReanalyze"
        >{{ store.projectRelinkReanalyzing ? '重新分析中...' : '重新分析 (继承绑定)' }}</button>

        <!-- D-4: Job chain toggle -->
        <button v-if="jobId" class="btn btn-sm" @click="doToggleJobChain">
          {{ showJobChain ? '收起任务链' : '任务链' }}
        </button>

        <!-- D-1: Apply now triggers preview confirmation -->
        <button
          v-if="hasRelinkedItems"
          class="btn btn-primary btn-sm"
          :disabled="store.projectRelinkApplying || store.projectRelinkPreviewLoading"
          @click="doPreviewApply"
        >
          {{ store.projectRelinkPreviewLoading ? '检查中...' : store.projectRelinkApplying ? '生成中...' : '生成修复副本' }}
        </button>
      </div>

      <!-- D-1+D-3: Apply confirmation panel with diff preview -->
      <div v-if="store.projectRelinkApplyConfirmVisible && previewApply" class="prp-confirm-panel">
        <div class="prp-confirm-title">确认生成修复副本</div>
        <div class="prp-confirm-stats">
          <span class="prp-confirm-ok">{{ previewApply.will_apply.length }} 个将修复</span>
          <span v-if="previewApply.will_skip.length" class="prp-confirm-skip">{{ previewApply.will_skip.length }} 个将跳过</span>
        </div>

        <!-- D-3: Summary from preview -->
        <div v-if="previewSummary" class="prp-confirm-summary-row">
          <span v-if="previewSummary.manual_bindings">🔧 {{ previewSummary.manual_bindings }} 人工绑定</span>
          <span v-if="previewSummary.system_matches">🤖 {{ previewSummary.system_matches }} 系统匹配</span>
        </div>

        <div v-if="previewApply.warnings && previewApply.warnings.length" class="prp-confirm-warnings">
          <div v-for="w in previewApply.warnings" :key="w" class="prp-confirm-warn-item">⚠️ {{ w }}</div>
        </div>

        <!-- D-3: Diff items toggle -->
        <div v-if="diffItems.length" class="prp-diff-toggle">
          <button class="btn btn-xs" @click="showDiffDetail = !showDiffDetail">
            {{ showDiffDetail ? '收起明细' : '展开差异明细 (' + diffItems.length + ')' }}
          </button>
        </div>
        <div v-if="showDiffDetail && diffItems.length" class="prp-diff-list">
          <div v-for="d in diffItems" :key="d.item_id" class="prp-diff-row" :class="{ 'prp-diff-skip': d.action === 'skip' }">
            <span class="prp-diff-action">{{ d.action === 'apply' ? '✅' : '⏭' }}</span>
            <span class="prp-diff-name">{{ d.asset_name }}</span>
            <span class="prp-diff-mode" :class="d.binding_mode === 'manual' ? 'prp-diff-manual' : 'prp-diff-system'">
              {{ bindingModeLabel(d.binding_mode) }}
            </span>
            <div class="prp-diff-paths">
              <span class="prp-path prp-path-old">{{ truncPath(d.old_path) }}</span>
              <template v-if="d.new_path">
                <span class="prp-arrow">→</span>
                <span class="prp-path prp-path-new">{{ truncPath(d.new_path) }}</span>
              </template>
              <span v-if="d.reason" class="prp-diff-reason">{{ d.reason }}</span>
            </div>
          </div>
        </div>

        <div class="prp-confirm-output">
          <span class="prp-confirm-label">输出路径：</span>
          <span class="prp-confirm-path">{{ truncPath(previewApply.output_path_preview) }}</span>
        </div>
        <div class="prp-confirm-actions">
          <button class="btn btn-primary btn-sm" @click="store.confirmApply()">确认执行</button>
          <button class="btn btn-sm" @click="store.cancelApplyConfirm()">取消</button>
        </div>
      </div>

      <!-- Apply result -->
      <div v-if="store.projectRelinkApplyResult" class="prp-apply-result">
        ✅ 修复副本已生成：{{ store.projectRelinkApplyResult.output_path }}
        <br/>已修复 {{ store.projectRelinkApplyResult.applied }} 个引用
        <span v-if="store.projectRelinkApplyResult.skipped">，跳过 {{ store.projectRelinkApplyResult.skipped }} 个</span>

        <div v-if="store.projectRelinkApplyResult.apply_detail" class="prp-apply-detail-toggle">
          <button class="btn btn-xs" @click="showApplyDetail = !showApplyDetail">
            {{ showApplyDetail ? '收起明细' : '展开明细' }}
          </button>
          <div v-if="showApplyDetail" class="prp-detail-list">
            <div v-for="ai in store.projectRelinkApplyResult.apply_detail.applied_items" :key="ai.item_id" class="prp-detail-row">
              ✅ {{ ai.asset_name }}: {{ truncPath(ai.old_path) }} → {{ truncPath(ai.new_path) }}
            </div>
            <div v-for="si in store.projectRelinkApplyResult.apply_detail.skipped_items" :key="si.item_id" class="prp-detail-row prp-detail-skip">
              ⏭ {{ si.asset_name }}: {{ si.reason }}
            </div>
          </div>
        </div>
      </div>

      <!-- D-3: Outputs list -->
      <div v-if="showOutputs && outputs.length" class="prp-outputs-section">
        <div class="prp-outputs-title">副本生成记录</div>
        <div v-for="o in outputs" :key="o.output_id" class="prp-output-row">
          <span class="prp-output-id">#{{ o.output_id }}</span>
          <span class="prp-output-path" :title="o.output_path">{{ truncPath(o.output_path) }}</span>
          <span class="prp-output-counts">{{ o.applied_count }}修复 / {{ o.skipped_count }}跳过</span>
          <span class="prp-output-time">{{ formatTime(o.created_at) }}</span>
        </div>
      </div>
      <div v-else-if="showOutputs && !outputs.length && !store.projectRelinkOutputsLoading" class="prp-outputs-empty">
        暂无副本生成记录
      </div>

      <!-- D-4: Job chain timeline -->
      <div v-if="showJobChain && store.projectRelinkJobChain.length" class="prp-job-chain">
        <div class="prp-chain-title">任务链时间线</div>
        <div v-for="(cj, ci) in store.projectRelinkJobChain" :key="cj.job_id" class="prp-chain-node">
          <div class="prp-chain-dot" :class="{ 'prp-chain-current': cj.job_id === jobId }"></div>
          <div class="prp-chain-line" v-if="ci < store.projectRelinkJobChain.length - 1"></div>
          <div class="prp-chain-info" @click="doLoadJob(cj.job_id)">
            <span class="prp-chain-id">#{{ cj.job_id }}</span>
            <span class="prp-chain-time">{{ formatTime(cj.created_at) }}</span>
            <span class="prp-job-status-badge" :class="'prp-js-' + cj.status">{{ jobStatusBadge(cj.status) }}</span>
            <span v-if="cj.inherited_count" class="prp-chain-inherit">继承 {{ cj.inherited_count }} 绑定</span>
            <span class="prp-chain-stats">{{ cj.changed_refs || 0 }}恢复 / {{ cj.missing_refs || 0 }}缺失</span>
            <span v-if="cj.apply_count" class="prp-chain-applied">已应用×{{ cj.apply_count }}</span>
            <span v-if="cj.handover_at" class="badge badge-success prp-handover-badge">已交接</span>
          </div>
        </div>
      </div>
      <div v-else-if="showJobChain && !store.projectRelinkJobChainLoading" class="prp-chain-empty">
        暂无任务链
      </div>

      <!-- D-4: Handover closure section -->
      <div v-if="jobId && store.projectRelinkJob?.status === 'done'" class="prp-handover-section">
        <div class="prp-section-header" @click="showHandover = !showHandover">
          <span>{{ showHandover ? '▾' : '▸' }} 交接闭环</span>
          <span v-if="store.projectRelinkJob?.handover_at" class="badge badge-success">已交接</span>
        </div>
        <div v-if="showHandover" class="prp-handover-body">
          <div class="prp-handover-actions-row">
            <button class="btn btn-xs" :disabled="store.projectRelinkVerifyLoading"
              @click="doVerify">
              {{ store.projectRelinkVerifyLoading ? '验证中...' : '验证路径有效性' }}
            </button>
            <button class="btn btn-primary btn-xs" :disabled="store.projectRelinkHandoverLoading"
              @click="doGenerateHandover">
              {{ store.projectRelinkHandoverLoading ? '生成中...' : '生成交接报告' }}
            </button>
          </div>

          <!-- Verification result (D-4 rule #3: separate from status) -->
          <div v-if="store.projectRelinkVerification" class="prp-verify-result">
            <span v-if="store.projectRelinkVerification.all_valid" class="prp-verify-pass">全部路径有效 ✓</span>
            <span v-else class="prp-verify-fail">{{ store.projectRelinkVerification.stale_count }} 个路径已失效 ⚠</span>
            <span class="prp-verify-count">已验证 {{ store.projectRelinkVerification.verified }} 项</span>
          </div>

          <!-- Handover report preview -->
          <div v-if="store.projectRelinkHandover" class="prp-handover-preview">
            <div class="prp-handover-status">
              状态: {{ store.projectRelinkHandover.closure_status === 'complete' ? '全部解决 ✓' : '仍有未解决项 ⚠' }}
            </div>
            <div v-if="store.projectRelinkHandover.resolution_summary" class="prp-handover-summary">
              <span>系统恢复 {{ store.projectRelinkHandover.resolution_summary.relinked_system || 0 }}</span>
              <span>人工绑定 {{ store.projectRelinkHandover.resolution_summary.relinked_manual || 0 }}</span>
              <span>缺失 {{ store.projectRelinkHandover.resolution_summary.missing || 0 }}</span>
            </div>
            <div class="prp-handover-export-row">
              <button class="btn btn-xs" @click="doExportHandover('json')">导出 JSON</button>
              <button class="btn btn-xs" @click="doExportHandover('markdown')">导出 Markdown</button>
            </div>
          </div>
        </div>
      </div>

      <!-- History -->
      <div v-if="store.projectRelinkJobHistory.length" class="prp-history">
        <div class="prp-history-title">历史记录</div>
        <div v-for="hj in store.projectRelinkJobHistory" :key="hj.job_id"
          class="prp-history-item"
        >
          <input type="checkbox" class="prp-compare-check"
            :value="hj.job_id"
            @change="e => {
              if (e.target.checked) {
                if (!compareJobA) compareJobA = hj.job_id
                else compareJobB = hj.job_id
              } else {
                if (compareJobA === hj.job_id) compareJobA = null
                else if (compareJobB === hj.job_id) compareJobB = null
              }
            }"
          />
          <span class="prp-history-id" @click="store.restoreProjectRelinkJob(hj.job_id)">#{{ hj.job_id }}</span>
          <!-- D-1: Status badge -->
          <span class="prp-job-status-badge" :class="'prp-js-' + hj.status">{{ jobStatusBadge(hj.status) }}</span>
          <span class="prp-history-time">{{ formatTime(hj.created_at) }}</span>
          <span class="prp-history-stats">
            {{ hj.changed_refs || 0 }}恢复 / {{ hj.missing_refs || 0 }}缺失
          </span>
          <span v-if="hj.apply_count" class="prp-history-applied">已应用×{{ hj.apply_count }}</span>
          <!-- D-4: Predecessor + handover badges in history -->
          <span v-if="hj.predecessor_job_id" class="prp-pred-badge">← #{{ hj.predecessor_job_id }}</span>
          <span v-if="hj.handover_at" class="badge badge-success prp-handover-badge">已交接</span>
          <!-- D-1: Retry button for failed jobs -->
          <button
            v-if="hj.status === 'failed'"
            class="btn btn-xs prp-retry-btn"
            :disabled="store.projectRelinkRetrying"
            @click="store.retryProjectRelinkJob(hj.job_id)"
          >{{ store.projectRelinkRetrying ? '重试中...' : '重试' }}</button>
          <span v-if="hj.retry_of" class="prp-retry-badge">重试自 #{{ hj.retry_of }}</span>
        </div>
        <button v-if="compareJobA && compareJobB" class="btn btn-sm" style="margin-top:6px"
          :disabled="store.projectRelinkCompareLoading"
          @click="doCompare"
        >
          {{ store.projectRelinkCompareLoading ? '对比中...' : '对比选中的两个任务' }}
        </button>
      </div>

      <!-- Compare result -->
      <div v-if="store.projectRelinkCompareResult && store.projectRelinkCompareResult.summary" class="prp-compare">
        <div class="prp-compare-title">
          Job #{{ store.projectRelinkCompareResult.job_id_a }} vs #{{ store.projectRelinkCompareResult.job_id_b }}
        </div>
        <div class="prp-compare-summary">
          <span class="prp-compare-stat prp-stat-relinked">+{{ store.projectRelinkCompareResult.summary.newly_relinked }} 新恢复</span>
          <span class="prp-compare-stat prp-stat-missing">+{{ store.projectRelinkCompareResult.summary.newly_missing }} 新缺失</span>
          <span class="prp-compare-stat prp-stat-unmatched">{{ store.projectRelinkCompareResult.summary.still_unmatched }} 持续未匹配</span>
          <span class="prp-compare-stat">{{ store.projectRelinkCompareResult.summary.total_changes }} 总变化</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prp-panel {
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  margin-bottom: 12px;
  background: var(--surface, #1a1a1a);
}
.prp-header {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  font-weight: 600;
  gap: 6px;
}
.prp-header:hover { background: rgba(255,255,255,0.03); }
.prp-chevron { font-size: 12px; opacity: 0.6; width: 14px; }
.prp-title { flex: 1; }
.prp-body { padding: 0 14px 14px; }

.prp-validation-warn {
  padding: 6px 10px;
  margin-bottom: 10px;
  border-radius: 4px;
  background: rgba(255,183,77,0.1);
  color: #ffb74d;
  font-size: 12px;
}

.prp-input-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.prp-input-row .form-input { flex: 1; }

.prp-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.prp-stat-card {
  flex: 1;
  min-width: 70px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(255,255,255,0.04);
  text-align: center;
}
.prp-stat-num { font-size: 20px; font-weight: 700; }
.prp-stat-label { font-size: 11px; opacity: 0.6; margin-top: 2px; }
.prp-stat-stable .prp-stat-num { color: #4caf50; }
.prp-stat-relinked .prp-stat-num { color: var(--accent, #5a8dee); }
.prp-stat-missing .prp-stat-num { color: #ef5350; }
.prp-stat-unmatched .prp-stat-num { color: #888; }

/* Filter bar */
.prp-filter-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.prp-filter-btn {
  padding: 3px 10px;
  border: 1px solid var(--border, #444);
  border-radius: 12px;
  background: transparent;
  color: #aaa;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.prp-filter-btn:hover { border-color: var(--accent, #5a8dee); color: #ccc; }
.prp-filter-btn.active {
  background: var(--accent, #5a8dee);
  color: #fff;
  border-color: var(--accent, #5a8dee);
}
.prp-filter-count { opacity: 0.7; font-size: 11px; }

.prp-items-list {
  max-height: 500px;
  overflow-y: auto;
  margin-bottom: 12px;
  border: 1px solid var(--border, #333);
  border-radius: 4px;
}
.prp-item {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.prp-item:last-child { border-bottom: none; }

.prp-status-badge {
  display: inline-block;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
  min-width: 48px;
  text-align: center;
}
.prp-s-stable { background: rgba(76,175,80,0.15); color: #4caf50; }
.prp-s-relinked { background: rgba(90,141,238,0.15); color: var(--accent, #5a8dee); }
.prp-s-missing { background: rgba(239,83,80,0.15); color: #ef5350; }
.prp-s-unmatched { background: rgba(136,136,136,0.15); color: #888; }

.prp-item-name {
  font-weight: 500;
  font-size: 13px;
  min-width: 80px;
}
.prp-media-type {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(255,255,255,0.06);
  color: #999;
  text-transform: uppercase;
}
.prp-match-tag {
  font-size: 10px;
  padding: 0 5px;
  border-radius: 3px;
  background: rgba(90,141,238,0.1);
  color: var(--accent, #5a8dee);
}
.prp-conf-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 0 4px;
  border-radius: 3px;
}
.prp-conf-high { background: rgba(76,175,80,0.15); color: #4caf50; }
.prp-conf-mid  { background: rgba(255,183,77,0.15); color: #ffb74d; }
.prp-conf-low  { background: rgba(239,83,80,0.15); color: #ef5350; }
.prp-item-paths {
  width: 100%;
  font-size: 12px;
  font-family: monospace;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding-left: 54px;
}
.prp-path { word-break: break-all; }
.prp-path-ok { color: #4caf50; }
.prp-path-old { color: #888; text-decoration: line-through; }
.prp-path-new { color: var(--accent, #5a8dee); }
.prp-path-miss { color: #ef5350; }
.prp-path-gray { color: #666; }
.prp-arrow { color: #666; margin: 0 2px; }
.prp-hint-text { color: #888; font-style: italic; font-size: 11px; }

/* D-1: Search jump button */
.prp-search-jump {
  font-size: 10px;
  color: var(--accent, #5a8dee);
  border-color: var(--accent, #5a8dee);
  opacity: 0.8;
}
.prp-search-jump:hover { opacity: 1; }

/* D-2: Binding badges */
.prp-bind-badge {
  display: inline-block;
  font-size: 10px;
  padding: 0 5px;
  border-radius: 3px;
  font-weight: 600;
}
.prp-bind-manual {
  background: rgba(76,175,80,0.15);
  color: #4caf50;
}
.prp-bind-system {
  background: rgba(90,141,238,0.1);
  color: var(--accent, #5a8dee);
}

/* D-2: Pending bind indicator */
.prp-pending-bind-badge {
  font-size: 10px;
  padding: 0 6px;
  border-radius: 3px;
  background: rgba(255,183,77,0.15);
  color: #ffb74d;
  font-weight: 600;
  margin-left: 6px;
}

/* D-2: Candidate button */
.prp-candidate-btn {
  font-size: 10px;
  color: #ffb74d;
  border-color: #ffb74d;
  opacity: 0.8;
}
.prp-candidate-btn:hover { opacity: 1; }

/* D-2: Search-bind button */
.prp-search-bind-btn {
  font-size: 10px;
  color: #ce93d8;
  border-color: #ce93d8;
  opacity: 0.8;
}
.prp-search-bind-btn:hover { opacity: 1; }

/* D-2: Unbind button */
.prp-unbind-btn {
  font-size: 10px;
  color: #ef5350;
  border-color: #ef5350;
  opacity: 0.8;
}
.prp-unbind-btn:hover { opacity: 1; background: rgba(239,83,80,0.1); }

/* D-2: Candidate suggestions panel */
.prp-candidates-panel {
  width: 100%;
  margin-top: 6px;
  padding: 8px 10px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px;
}
.prp-candidates-loading,
.prp-candidates-empty {
  font-size: 12px;
  color: #888;
  text-align: center;
  padding: 6px 0;
}
.prp-candidates-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.prp-candidate-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 3px;
  font-size: 12px;
}
.prp-candidate-row:hover { background: rgba(255,255,255,0.04); }
.prp-candidate-name {
  flex: 1;
  font-family: monospace;
  word-break: break-all;
  color: #ccc;
}
.prp-candidate-score {
  font-weight: 600;
  color: var(--accent, #5a8dee);
  min-width: 36px;
  text-align: right;
}
.prp-candidate-avail {
  font-size: 10px;
  color: #4caf50;
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(76,175,80,0.1);
}
.prp-candidate-unavail {
  font-size: 10px;
  color: #888;
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(136,136,136,0.1);
}
.prp-candidate-bind-btn {
  font-size: 10px;
  color: #4caf50;
  border-color: #4caf50;
  font-weight: 600;
}
.prp-candidate-bind-btn:hover { background: rgba(76,175,80,0.1); }

.prp-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: flex-start;
}

/* D-1: Dropdown for export missing */
.prp-dropdown-wrap {
  position: relative;
  display: inline-block;
}
.prp-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 10;
  background: var(--surface, #1a1a1a);
  border: 1px solid var(--border, #444);
  border-radius: 4px;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  margin-top: 2px;
}
.prp-dropdown-item {
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  color: #ccc;
}
.prp-dropdown-item:hover {
  background: rgba(255,255,255,0.06);
  color: #fff;
}

/* D-1: Apply confirmation panel */
.prp-confirm-panel {
  margin-top: 10px;
  padding: 12px;
  border-radius: 6px;
  background: rgba(90,141,238,0.06);
  border: 1px solid rgba(90,141,238,0.2);
}
.prp-confirm-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}
.prp-confirm-stats {
  display: flex;
  gap: 12px;
  margin-bottom: 6px;
  font-size: 13px;
}
.prp-confirm-ok { color: #4caf50; font-weight: 600; }
.prp-confirm-skip { color: #ffb74d; font-weight: 600; }
.prp-confirm-warnings {
  margin-bottom: 8px;
}
.prp-confirm-warn-item {
  font-size: 12px;
  color: #ffb74d;
  padding: 2px 0;
}
.prp-confirm-output {
  font-size: 12px;
  margin-bottom: 10px;
  color: #aaa;
}
.prp-confirm-label { font-weight: 600; }
.prp-confirm-path { font-family: monospace; word-break: break-all; }
.prp-confirm-actions {
  display: flex;
  gap: 8px;
}

.prp-apply-result {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 4px;
  background: rgba(76,175,80,0.1);
  color: #4caf50;
  font-size: 13px;
  word-break: break-all;
}
.prp-apply-detail-toggle { margin-top: 6px; }
.prp-detail-list {
  margin-top: 6px;
  padding: 6px 0;
  font-size: 12px;
}
.prp-detail-row {
  padding: 2px 0;
  font-family: monospace;
  font-size: 11px;
}
.prp-detail-skip { color: #888; }

.prp-empty {
  text-align: center;
  padding: 20px;
  opacity: 0.5;
}

/* History */
.prp-history {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--border, #333);
}
.prp-history-title {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.6;
  margin-bottom: 6px;
}
.prp-history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.prp-compare-check { width: 14px; height: 14px; cursor: pointer; }
.prp-history-id {
  color: var(--accent, #5a8dee);
  cursor: pointer;
  font-weight: 600;
  min-width: 36px;
}
.prp-history-id:hover { text-decoration: underline; }

/* D-1: Job status badges in history */
.prp-job-status-badge {
  display: inline-block;
  font-size: 10px;
  padding: 0 5px;
  border-radius: 3px;
  font-weight: 600;
  min-width: 36px;
  text-align: center;
}
.prp-js-done { background: rgba(76,175,80,0.15); color: #4caf50; }
.prp-js-failed { background: rgba(239,83,80,0.15); color: #ef5350; }
.prp-js-running { background: rgba(90,141,238,0.15); color: var(--accent, #5a8dee); }
.prp-js-pending { background: rgba(136,136,136,0.15); color: #888; }

/* D-1: Retry button + badge */
.prp-retry-btn {
  font-size: 10px;
  color: #ef5350;
  border-color: #ef5350;
}
.prp-retry-btn:hover { background: rgba(239,83,80,0.1); }
.prp-retry-badge {
  font-size: 10px;
  color: #888;
  font-style: italic;
}

.prp-history-time { color: #888; min-width: 100px; }
.prp-history-stats { color: #aaa; flex: 1; }
.prp-history-applied {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(76,175,80,0.15);
  color: #4caf50;
}

/* Compare */
.prp-compare {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 4px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--border, #333);
}
.prp-compare-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}
.prp-compare-summary {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.prp-compare-stat {
  font-size: 12px;
  font-weight: 600;
}
.prp-compare-stat.prp-stat-relinked { color: var(--accent, #5a8dee); }
.prp-compare-stat.prp-stat-missing { color: #ef5350; }
.prp-compare-stat.prp-stat-unmatched { color: #888; }

/* ── D-3: Workbench tabs ── */
.prp-workbench-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.prp-wb-tab {
  padding: 4px 12px;
  border: 1px solid var(--border, #444);
  border-radius: 4px 4px 0 0;
  background: transparent;
  color: #aaa;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  border-bottom: 2px solid transparent;
}
.prp-wb-tab:hover { color: #ccc; border-bottom-color: rgba(90,141,238,0.3); }
.prp-wb-tab.active {
  color: #fff;
  border-bottom-color: var(--accent, #5a8dee);
  background: rgba(90,141,238,0.06);
}
.prp-wb-count { opacity: 0.6; font-size: 11px; }
.prp-wb-spacer { flex: 1; }

/* D-3: Batch mode */
.prp-batch-toggle {
  font-size: 10px;
  color: #ce93d8;
  border-color: #ce93d8;
}
.prp-batch-toggle:hover { background: rgba(206,147,216,0.1); }
.prp-batch-active {
  background: rgba(206,147,216,0.15);
  color: #ce93d8;
  border-color: #ce93d8;
}
.prp-batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 8px;
  border-radius: 4px;
  background: rgba(206,147,216,0.08);
  border: 1px solid rgba(206,147,216,0.2);
}
.prp-batch-info {
  font-size: 12px;
  color: #ce93d8;
  font-weight: 600;
}
.prp-batch-check {
  width: 14px;
  height: 14px;
  cursor: pointer;
  flex-shrink: 0;
}

/* D-3: Undo button */
.prp-undo-btn {
  font-size: 10px;
  color: #ffb74d;
  border-color: #ffb74d;
  opacity: 0.8;
}
.prp-undo-btn:hover { opacity: 1; background: rgba(255,183,77,0.1); }

/* D-3: Item history button */
.prp-history-btn {
  font-size: 10px;
  color: #90caf9;
  border-color: #90caf9;
  opacity: 0.8;
}
.prp-history-btn:hover { opacity: 1; }

/* D-3: Item history drawer */
.prp-item-history-drawer {
  width: 100%;
  margin-top: 6px;
  padding: 8px 10px;
  background: rgba(144,202,249,0.04);
  border: 1px solid rgba(144,202,249,0.15);
  border-radius: 4px;
}
.prp-ih-loading,
.prp-ih-empty {
  font-size: 12px;
  color: #888;
  text-align: center;
  padding: 4px 0;
}
.prp-ih-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.prp-ih-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 3px;
}
.prp-ih-row:hover { background: rgba(255,255,255,0.03); }
.prp-ih-type {
  display: inline-block;
  padding: 0 5px;
  border-radius: 3px;
  font-weight: 600;
  font-size: 10px;
  min-width: 52px;
  text-align: center;
}
.prp-ih-bind { background: rgba(76,175,80,0.15); color: #4caf50; }
.prp-ih-unbind { background: rgba(239,83,80,0.15); color: #ef5350; }
.prp-ih-undo_bind { background: rgba(255,183,77,0.15); color: #ffb74d; }
.prp-ih-time { color: #888; min-width: 100px; }
.prp-ih-detail {
  color: #777;
  font-family: monospace;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

/* D-3: Diff preview in confirm panel */
.prp-confirm-summary-row {
  display: flex;
  gap: 12px;
  margin-bottom: 6px;
  font-size: 12px;
  color: #aaa;
}
.prp-diff-toggle {
  margin: 6px 0;
}
.prp-diff-list {
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 8px;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 4px;
}
.prp-diff-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.prp-diff-row:last-child { border-bottom: none; }
.prp-diff-skip { opacity: 0.5; }
.prp-diff-action { font-size: 12px; flex-shrink: 0; }
.prp-diff-name { font-weight: 500; min-width: 80px; }
.prp-diff-mode {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 3px;
  font-weight: 600;
}
.prp-diff-manual { background: rgba(76,175,80,0.15); color: #4caf50; }
.prp-diff-system { background: rgba(90,141,238,0.1); color: var(--accent, #5a8dee); }
.prp-diff-paths {
  width: 100%;
  padding-left: 24px;
  font-family: monospace;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.prp-diff-reason {
  color: #888;
  font-style: italic;
  font-size: 10px;
}

/* D-3: Outputs section */
.prp-outputs-section {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 4px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border, #333);
}
.prp-outputs-title {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.7;
  margin-bottom: 6px;
}
.prp-output-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.prp-output-row:last-child { border-bottom: none; }
.prp-output-id {
  color: var(--accent, #5a8dee);
  font-weight: 600;
  min-width: 32px;
}
.prp-output-path {
  font-family: monospace;
  font-size: 11px;
  color: #ccc;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.prp-output-counts {
  color: #888;
  font-size: 11px;
  min-width: 80px;
}
.prp-output-time {
  color: #777;
  font-size: 11px;
  min-width: 100px;
}
.prp-outputs-empty {
  margin-top: 10px;
  text-align: center;
  font-size: 12px;
  color: #666;
  padding: 8px;
}

/* ── D-4: Long-term sync + handover ── */

/* Predecessor info bar */
.prp-predecessor-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 8px;
  background: rgba(90,141,238,0.08);
  border-radius: 4px;
  font-size: 12px;
}
.prp-pred-label { color: #888; }
.prp-pred-link { color: var(--accent, #5a8dee); cursor: pointer; font-weight: 600; }
.prp-pred-link:hover { text-decoration: underline; }
.prp-pred-count { color: #4caf50; font-size: 11px; }
.prp-pred-badge { font-size: 10px; color: #888; }
.prp-handover-badge { font-size: 10px; }

/* Inherited binding badge */
.prp-bind-inherited {
  background: rgba(255,152,0,0.15);
  color: #ff9800;
}

/* Verify health badges (D-4 rule #3: separate from status) */
.prp-health-badge {
  display: inline-block;
  font-size: 9px;
  padding: 0 4px;
  border-radius: 3px;
  font-weight: 600;
}
.prp-health-valid { background: rgba(76,175,80,0.12); color: #4caf50; }
.prp-health-stale { background: rgba(239,83,80,0.12); color: #ef5350; }
.prp-health-unchecked { background: rgba(136,136,136,0.12); color: #888; }

/* Job chain timeline */
.prp-job-chain {
  margin: 10px 0;
  padding: 8px 10px;
  background: var(--surface-alt, #222);
  border-radius: 4px;
}
.prp-chain-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #ccc;
}
.prp-chain-node {
  position: relative;
  padding-left: 20px;
  margin-bottom: 4px;
}
.prp-chain-dot {
  position: absolute;
  left: 4px;
  top: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #555;
}
.prp-chain-dot.prp-chain-current { background: var(--accent, #5a8dee); }
.prp-chain-line {
  position: absolute;
  left: 7px;
  top: 14px;
  width: 2px;
  height: 16px;
  background: #444;
}
.prp-chain-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  cursor: pointer;
  flex-wrap: wrap;
}
.prp-chain-info:hover { color: var(--accent, #5a8dee); }
.prp-chain-id { font-weight: 600; }
.prp-chain-time { color: #777; font-size: 11px; }
.prp-chain-inherit { color: #ff9800; font-size: 11px; }
.prp-chain-stats { color: #888; font-size: 11px; }
.prp-chain-applied { color: #4caf50; font-size: 11px; }
.prp-chain-empty {
  margin: 10px 0;
  text-align: center;
  font-size: 12px;
  color: #666;
}

/* Handover closure section */
.prp-handover-section {
  margin: 10px 0;
  border: 1px solid var(--border, #333);
  border-radius: 4px;
}
.prp-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.prp-section-header:hover { background: rgba(255,255,255,0.03); }
.prp-handover-body {
  padding: 8px 10px;
  border-top: 1px solid var(--border, #333);
}
.prp-handover-actions-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.prp-verify-result {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 8px;
}
.prp-verify-pass { color: #4caf50; font-weight: 600; }
.prp-verify-fail { color: #ef5350; font-weight: 600; }
.prp-verify-count { color: #888; font-size: 11px; }
.prp-handover-preview {
  margin-top: 8px;
  padding: 8px;
  background: var(--surface-alt, #222);
  border-radius: 4px;
}
.prp-handover-status { font-size: 12px; margin-bottom: 4px; }
.prp-handover-summary {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #aaa;
  margin-bottom: 8px;
}
.prp-handover-export-row {
  display: flex;
  gap: 8px;
}
</style>
