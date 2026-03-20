<template>
  <div class="sap-panel">
    <div class="sap-header" @click="expanded = !expanded">
      <span class="sap-title">搜索分析</span>
      <span class="sap-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-if="expanded" class="sap-body">
      <!-- Tab bar -->
      <div class="sap-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="sap-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >{{ tab.label }}</button>
      </div>

      <div v-if="loading" class="sap-loading">加载中...</div>

      <!-- Popular searches -->
      <div v-else-if="activeTab === 'popular'" class="sap-section">
        <div v-if="popular.length === 0" class="sap-empty">暂无搜索记录</div>
        <div v-else class="sap-list">
          <div v-for="(item, i) in popular" :key="i" class="sap-row" @click="$emit('search-query', item.query)">
            <span class="sap-rank">{{ i + 1 }}</span>
            <span class="sap-query">{{ item.query }}</span>
            <span class="sap-count">{{ item.count }}次</span>
            <span v-if="item.avg_results !== undefined" class="sap-meta">
              平均{{ item.avg_results }}条
            </span>
          </div>
        </div>
      </div>

      <!-- Zero-hit queries -->
      <div v-else-if="activeTab === 'zerohit'" class="sap-section">
        <div v-if="zeroHits.length === 0" class="sap-empty">暂无零结果搜索</div>
        <div v-else class="sap-list">
          <div v-for="(item, i) in zeroHits" :key="i" class="sap-row sap-row-warn">
            <span class="sap-rank">{{ i + 1 }}</span>
            <span class="sap-query">{{ item.query }}</span>
            <span class="sap-count">{{ item.count }}次</span>
            <span class="sap-badge-zero">无结果</span>
          </div>
        </div>
      </div>

      <!-- Learning candidates -->
      <div v-else-if="activeTab === 'candidates'" class="sap-section">
        <div class="sap-filter-row">
          <select v-model="candidateSource" class="form-select sap-filter-select" @change="loadCandidates">
            <option value="">全部来源</option>
            <option value="search_query">搜索</option>
            <option value="ingest">入库</option>
          </select>
          <select v-model="candidateStatus" class="form-select sap-filter-select" @change="loadCandidates">
            <option value="pending">待审核</option>
            <option value="approved">已通过</option>
            <option value="rejected">已拒绝</option>
            <option value="blocked">已屏蔽</option>
          </select>
          <button
            class="btn btn-ghost sap-classify-btn"
            :disabled="classifying"
            @click="classifyCandidates"
            title="自动分析候选词并推荐操作"
          >{{ classifying ? '分析中...' : '自动分类' }}</button>
          <button
            class="btn btn-ghost sap-classify-btn"
            :disabled="batchRejecting"
            @click="batchRejectNoise"
            title="批量屏蔽所有已标记为噪音的候选词"
          >{{ batchRejecting ? '处理中...' : '批量清噪' }}</button>
        </div>
        <div v-if="classifyResult" class="sap-classify-result">
          已分析 {{ classifyResult.classified }} 个候选词：
          <span v-for="(cnt, act) in classifyResult.actions" :key="act" class="sap-badge-action" :class="`action-${act}`" style="margin-left: 4px">
            {{ actionLabel(act) }} {{ cnt }}
          </span>
        </div>
        <div v-if="candidates.length === 0" class="sap-empty">暂无候选词</div>
        <div v-else class="sap-list">
          <div v-for="c in candidates" :key="c.candidate_id" class="sap-row sap-row-candidate">
            <span class="sap-candidate-text">{{ c.candidate_text }}</span>
            <span class="sap-candidate-source">{{ sourceLabel(c.source_kind) }}</span>
            <span class="sap-count">{{ c.occurrence_count }}次/{{ c.asset_count }}素材</span>
            <span v-if="c.suggested_action && c.suggested_action !== 'review'" class="sap-badge-action" :class="`action-${c.suggested_action}`">
              {{ actionLabel(c.suggested_action) }}
            </span>
            <span v-if="c.cooccur_summary" class="sap-cooccur" :title="c.cooccur_summary">
              {{ c.cooccur_summary }}
            </span>
            <div v-if="c.review_status === 'pending'" class="sap-candidate-actions">
              <button
                v-if="c.suggested_action && c.suggested_action !== 'review' && c.suggested_action !== 'reject_noise'"
                class="sap-act-btn sap-act-promote"
                title="执行推荐操作（合并别名/升级标签）"
                @click="promoteCandidate(c.candidate_id)"
              >⬆</button>
              <button class="sap-act-btn sap-act-approve" title="通过" @click="reviewCandidate(c.candidate_id, 'approve')">✓</button>
              <button class="sap-act-btn sap-act-reject" title="拒绝" @click="reviewCandidate(c.candidate_id, 'reject')">✗</button>
              <button class="sap-act-btn sap-act-block" title="屏蔽" @click="reviewCandidate(c.candidate_id, 'block')">⊘</button>
            </div>
            <span v-else class="sap-badge-status" :class="`status-${c.review_status}`">
              {{ statusLabel(c.review_status) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Summary stats -->
      <div v-else-if="activeTab === 'summary'" class="sap-section">
        <div v-if="!summary" class="sap-empty">暂无统计数据</div>
        <div v-else class="sap-stats-grid">
          <div class="sap-stat-card">
            <div class="sap-stat-value">{{ summary.total_searches }}</div>
            <div class="sap-stat-label">总搜索次数</div>
          </div>
          <div class="sap-stat-card">
            <div class="sap-stat-value">{{ summary.unique_queries }}</div>
            <div class="sap-stat-label">独立查询数</div>
          </div>
          <div class="sap-stat-card sap-stat-warn">
            <div class="sap-stat-value">{{ summary.zero_hit_count }}</div>
            <div class="sap-stat-label">零结果搜索</div>
          </div>
          <div class="sap-stat-card">
            <div class="sap-stat-value">{{ summary.avg_results != null ? summary.avg_results.toFixed(1) : '-' }}</div>
            <div class="sap-stat-label">平均结果数</div>
          </div>
          <div class="sap-stat-card">
            <div class="sap-stat-value">{{ summary.avg_duration_ms != null ? summary.avg_duration_ms + 'ms' : '-' }}</div>
            <div class="sap-stat-label">平均耗时</div>
          </div>
          <div class="sap-stat-card">
            <div class="sap-stat-value">{{ summary.zero_hit_rate != null ? (summary.zero_hit_rate * 100).toFixed(1) + '%' : '-' }}</div>
            <div class="sap-stat-label">零结果率</div>
          </div>
        </div>
      </div>

      <!-- Review feedback -->
      <div v-if="reviewMessage" class="sap-message" :class="reviewMessageType">{{ reviewMessage }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useApiStore } from '../../stores/api.js'

const emit = defineEmits(['search-query'])

const api = useApiStore()
const expanded = ref(false)
const loading = ref(false)
const activeTab = ref('popular')

const tabs = [
  { key: 'popular', label: '热门搜索' },
  { key: 'zerohit', label: '零结果' },
  { key: 'candidates', label: '候选词' },
  { key: 'summary', label: '统计' },
]

// Data
const popular = ref([])
const zeroHits = ref([])
const candidates = ref([])
const summary = ref(null)

// Candidate filters
const candidateSource = ref('')
const candidateStatus = ref('pending')

// Classify & batch
const classifying = ref(false)
const classifyResult = ref(null)
const batchRejecting = ref(false)

// Review feedback
const reviewMessage = ref('')
const reviewMessageType = ref('info')

function sourceLabel(kind) {
  const map = { search_query: '搜索', ingest: '入库', ocr: 'OCR', asr: 'ASR' }
  return map[kind] || kind
}

function actionLabel(action) {
  const map = {
    review: '待定',
    merge_to_alias: '合并别名',
    upgrade_to_new_tag: '升级标签',
    become_rule_trigger: '规则触发',
    reject_noise: '噪音',
  }
  return map[action] || action
}

function statusLabel(status) {
  const map = { pending: '待审', approved: '已通过', rejected: '已拒绝', blocked: '已屏蔽' }
  return map[status] || status
}

async function loadPopular() {
  loading.value = true
  const data = await api.api('GET', '/api/library/search-analytics/popular?limit=30')
  loading.value = false
  if (data.error) return
  popular.value = data.popular_queries || []
}

async function loadZeroHits() {
  loading.value = true
  const data = await api.api('GET', '/api/library/search-analytics/zero-hits?limit=30')
  loading.value = false
  if (data.error) return
  zeroHits.value = data.zero_hit_queries || []
}

async function loadCandidates() {
  loading.value = true
  let url = '/api/library/learning-candidates?limit=50'
  if (candidateSource.value) url += `&source_kind=${candidateSource.value}`
  url += `&status=${candidateStatus.value}`
  const data = await api.api('GET', url)
  loading.value = false
  if (data.error) return
  // Parse cooccur_json into a display-friendly summary
  candidates.value = (data.candidates || []).map(c => {
    let cooccur_summary = ''
    if (c.cooccur_json) {
      try {
        const co = typeof c.cooccur_json === 'string' ? JSON.parse(c.cooccur_json) : c.cooccur_json
        if (co.merge_target_name) {
          cooccur_summary = `→${co.merge_target_name}`
        } else if (co.cooccurring_tags) {
          cooccur_summary = co.cooccurring_tags.slice(0, 3).map(t => t.tag_name).join(',')
        }
      } catch { /* ignore */ }
    }
    return { ...c, cooccur_summary }
  })
}

async function classifyCandidates() {
  classifying.value = true
  classifyResult.value = null
  const data = await api.api('POST', '/api/library/learning-candidates/classify', { limit: 200 })
  classifying.value = false
  if (data.error) {
    reviewMessage.value = data.error
    reviewMessageType.value = 'error'
    return
  }
  classifyResult.value = data
  // Refresh candidate list to show updated classifications
  await loadCandidates()
  // Clear result after 5s
  setTimeout(() => { classifyResult.value = null }, 5000)
}

async function promoteCandidate(candidateId) {
  reviewMessage.value = ''
  const data = await api.api('POST', `/api/library/learning-candidates/${candidateId}/promote`)
  if (data.error) {
    reviewMessage.value = data.error
    reviewMessageType.value = 'error'
    return
  }
  const parts = []
  if (data.created_alias) parts.push(`别名 "${data.created_alias}" → ${data.target_tag_name}`)
  if (data.created_tag_id) parts.push(`新标签 "${data.candidate_text}" (${data.semantic_slot})`)
  if (data.blocked) parts.push(`已屏蔽 "${data.candidate_text}"`)
  if (data.note) parts.push(data.note)
  reviewMessage.value = parts.length > 0 ? parts.join('；') : '操作成功'
  reviewMessageType.value = 'success'
  await loadCandidates()
  setTimeout(() => { reviewMessage.value = '' }, 3000)
}

async function batchRejectNoise() {
  batchRejecting.value = true
  reviewMessage.value = ''
  const data = await api.api('POST', '/api/library/learning-candidates/batch-reject-noise')
  batchRejecting.value = false
  if (data.error) {
    reviewMessage.value = data.error
    reviewMessageType.value = 'error'
    return
  }
  reviewMessage.value = `已批量屏蔽 ${data.rejected} 个噪音候选词`
  reviewMessageType.value = 'success'
  await loadCandidates()
  setTimeout(() => { reviewMessage.value = '' }, 3000)
}

async function loadSummary() {
  loading.value = true
  const data = await api.api('GET', '/api/library/search-analytics?days=30')
  loading.value = false
  if (data.error) return
  summary.value = data.summary || null
  // Also populate popular & zero-hit from analytics response if available
  if (data.popular_queries && popular.value.length === 0) {
    popular.value = data.popular_queries
  }
  if (data.zero_hit_queries && zeroHits.value.length === 0) {
    zeroHits.value = data.zero_hit_queries
  }
}

async function reviewCandidate(candidateId, action) {
  reviewMessage.value = ''
  const data = await api.api('POST', `/api/library/learning-candidates/${candidateId}/review`, { action })
  if (data.error) {
    reviewMessage.value = data.error
    reviewMessageType.value = 'error'
    return
  }
  reviewMessage.value = data.message || '操作成功'
  reviewMessageType.value = 'success'
  // Refresh candidates list
  await loadCandidates()
  // Clear message after 2s
  setTimeout(() => { reviewMessage.value = '' }, 2000)
}

watch(expanded, (val) => {
  if (val) {
    loadDataForTab(activeTab.value)
  }
})

watch(activeTab, (tab) => {
  reviewMessage.value = ''
  loadDataForTab(tab)
})

function loadDataForTab(tab) {
  if (tab === 'popular') loadPopular()
  else if (tab === 'zerohit') loadZeroHits()
  else if (tab === 'candidates') loadCandidates()
  else if (tab === 'summary') loadSummary()
}
</script>

<style scoped>
.sap-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
}

.sap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  background: var(--surface2);
  user-select: none;
}

.sap-header:hover {
  background: var(--surface3, rgba(255,255,255,0.06));
}

.sap-title {
  font-size: 13px;
  font-weight: 600;
}

.sap-toggle {
  font-size: 12px;
  color: var(--muted);
}

.sap-body {
  padding: 10px 12px;
}

/* Tabs */
.sap-tabs {
  display: flex;
  gap: 2px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
}

.sap-tab {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  color: var(--muted);
  transition: all 0.15s;
}

.sap-tab:hover {
  background: rgba(255,255,255,0.04);
  color: var(--fg);
}

.sap-tab.active {
  background: rgba(90, 141, 238, 0.12);
  color: var(--accent);
  font-weight: 600;
}

/* Sections */
.sap-section {
  max-height: 320px;
  overflow-y: auto;
}

.sap-loading,
.sap-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 12px 0;
  text-align: center;
}

/* List rows */
.sap-list {
  display: flex;
  flex-direction: column;
}

.sap-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 4px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px;
  cursor: default;
}

.sap-row:last-child {
  border-bottom: none;
}

.sap-row:not(.sap-row-candidate):hover {
  background: rgba(255,255,255,0.03);
  cursor: pointer;
}

.sap-rank {
  width: 20px;
  text-align: center;
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

.sap-query {
  flex: 1;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sap-count {
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

.sap-meta {
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

.sap-badge-zero {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(239, 83, 80, 0.12);
  color: #ef5350;
  flex-shrink: 0;
}

.sap-row-warn .sap-query {
  color: #ffb74d;
}

/* Candidate rows */
.sap-row-candidate {
  cursor: default;
  flex-wrap: wrap;
}

.sap-candidate-text {
  flex: 1;
  font-weight: 500;
  min-width: 80px;
}

.sap-candidate-source {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(255,255,255,0.06);
  color: var(--muted);
  flex-shrink: 0;
}

.sap-badge-action {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.action-review {
  background: rgba(255, 183, 77, 0.12);
  color: #ffb74d;
}

.action-merge_to_alias {
  background: rgba(90, 141, 238, 0.12);
  color: var(--accent);
}

.action-upgrade_to_new_tag {
  background: rgba(76, 175, 80, 0.12);
  color: #4caf50;
}

.action-become_rule_trigger {
  background: rgba(171, 71, 188, 0.12);
  color: #ab47bc;
}

.action-reject_noise {
  background: rgba(239, 83, 80, 0.12);
  color: #ef5350;
}

.sap-candidate-actions {
  display: flex;
  gap: 3px;
  flex-shrink: 0;
}

.sap-act-btn {
  background: none;
  border: 1px solid rgba(255,255,255,0.08);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 3px;
  transition: all 0.15s;
  line-height: 1;
}

.sap-act-approve:hover {
  background: rgba(76, 175, 80, 0.15);
  color: #4caf50;
  border-color: rgba(76, 175, 80, 0.3);
}

.sap-act-reject:hover {
  background: rgba(239, 83, 80, 0.15);
  color: #ef5350;
  border-color: rgba(239, 83, 80, 0.3);
}

.sap-act-block:hover {
  background: rgba(255, 183, 77, 0.15);
  color: #ffb74d;
  border-color: rgba(255, 183, 77, 0.3);
}

.sap-act-promote:hover {
  background: rgba(90, 141, 238, 0.15);
  color: var(--accent);
  border-color: rgba(90, 141, 238, 0.3);
}

.sap-badge-status {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.status-approved {
  background: rgba(76, 175, 80, 0.12);
  color: #4caf50;
}

.status-rejected {
  background: rgba(239, 83, 80, 0.12);
  color: #ef5350;
}

.status-blocked {
  background: rgba(255, 183, 77, 0.12);
  color: #ffb74d;
}

/* Candidate filter row */
.sap-filter-row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.sap-filter-select {
  font-size: 11px;
  padding: 4px 6px;
  width: 100px;
}

.sap-classify-btn {
  font-size: 11px;
  padding: 4px 10px;
  white-space: nowrap;
  margin-left: auto;
}

.sap-classify-result {
  font-size: 11px;
  padding: 4px 6px;
  margin-bottom: 8px;
  border-radius: 3px;
  background: rgba(76, 175, 80, 0.08);
  color: var(--fg);
}

.sap-cooccur {
  font-size: 10px;
  color: var(--accent);
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}

/* Summary stats grid */
.sap-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.sap-stat-card {
  text-align: center;
  padding: 10px 6px;
  border-radius: 6px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
}

.sap-stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1.2;
}

.sap-stat-warn .sap-stat-value {
  color: #ffb74d;
}

.sap-stat-label {
  font-size: 10px;
  color: var(--muted);
  margin-top: 3px;
}

/* Review feedback */
.sap-message {
  font-size: 11px;
  margin-top: 8px;
  padding: 3px 6px;
  border-radius: 3px;
}

.sap-message.success {
  color: #4caf50;
  background: rgba(76, 175, 80, 0.1);
}

.sap-message.error {
  color: #ef5350;
  background: rgba(239, 83, 80, 0.1);
}

.sap-message.info {
  color: var(--muted);
  background: rgba(255,255,255,0.04);
}
</style>
