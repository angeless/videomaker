<template>
  <div class="lhp-panel">
    <div class="lhp-header" @click="toggle">
      <span class="lhp-title">素材库健康</span>
      <span class="lhp-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-if="expanded" class="lhp-body">
      <div v-if="loading" class="lhp-loading">加载中...</div>

      <template v-else-if="health">
        <!-- Tab bar -->
        <div class="lhp-tabs">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="lhp-tab"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >{{ tab.label }}</button>
        </div>

        <!-- Coverage overview -->
        <div v-if="activeTab === 'coverage'" class="lhp-section">
          <div class="lhp-stats-grid">
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.asset_coverage.total_assets }}</div>
              <div class="lhp-stat-label">总素材数</div>
            </div>
            <div class="lhp-stat-card accent">
              <div class="lhp-stat-value">{{ health.asset_coverage.tag_coverage_pct }}%</div>
              <div class="lhp-stat-label">标签覆盖率</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.asset_coverage.with_tags }}</div>
              <div class="lhp-stat-label">已标签</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.asset_coverage.with_evidence }}</div>
              <div class="lhp-stat-label">有证据</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.asset_coverage.with_embedding }}</div>
              <div class="lhp-stat-label">有向量</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.asset_coverage.evidence_coverage_pct }}%</div>
              <div class="lhp-stat-label">证据覆盖率</div>
            </div>
          </div>

          <!-- Coverage bar -->
          <div class="lhp-bar-section" v-if="health.asset_coverage.total_assets > 0">
            <div class="lhp-bar-label">标签覆盖</div>
            <div class="lhp-bar-track">
              <div
                class="lhp-bar-fill"
                :style="{ width: health.asset_coverage.tag_coverage_pct + '%' }"
              ></div>
            </div>
            <span class="lhp-bar-pct">{{ health.asset_coverage.tag_coverage_pct }}%</span>
          </div>

          <!-- 补生成缩略图 -->
          <div class="lhp-subsection">
            <button
              class="btn btn-sm"
              :disabled="thumbLoading"
              @click="generateThumbnails"
            >{{ thumbLoading ? `生成中 ${thumbProgress}%…` : '补生成缩略图' }}</button>
            <span v-if="thumbResult" class="lhp-thumb-result">
              生成 {{ thumbResult.generated }}，跳过 {{ thumbResult.skipped }}，失败 {{ thumbResult.failed }}
            </span>
          </div>
        </div>

        <!-- Tag distribution by semantic slot -->
        <div v-else-if="activeTab === 'distribution'" class="lhp-section">
          <div v-if="health.tag_distribution.length === 0" class="lhp-empty">暂无标签分布数据</div>
          <div v-else class="lhp-list">
            <div
              v-for="slot in health.tag_distribution"
              :key="slot.semantic_slot"
              class="lhp-dist-row"
            >
              <span class="lhp-slot-name">{{ slotLabel(slot.semantic_slot) }}</span>
              <span class="lhp-slot-tags">{{ slot.tag_count }}标签</span>
              <div class="lhp-mini-bar-track">
                <div
                  class="lhp-mini-bar-fill"
                  :style="{ width: slot.coverage_pct + '%' }"
                ></div>
              </div>
              <span class="lhp-slot-pct">{{ slot.coverage_pct }}%</span>
              <span class="lhp-slot-count">{{ slot.asset_count }}素材</span>
            </div>
          </div>

          <!-- Top tags -->
          <div v-if="health.top_tags.length > 0" class="lhp-subsection">
            <div class="lhp-subsection-title">热门标签 TOP 10</div>
            <div class="lhp-tag-cloud">
              <span
                v-for="(tag, i) in health.top_tags.slice(0, 10)"
                :key="i"
                class="lhp-tag-chip"
                :title="slotLabel(tag.semantic_slot)"
              >{{ tag.tag_name }} <small>{{ tag.asset_count }}</small></span>
            </div>
          </div>
        </div>

        <!-- Quality metrics -->
        <div v-else-if="activeTab === 'quality'" class="lhp-section">
          <div class="lhp-stats-grid">
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.quality_metrics.avg_effective_score.toFixed(2) }}</div>
              <div class="lhp-stat-label">平均有效分</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.quality_metrics.avg_tags_per_asset.toFixed(1) }}</div>
              <div class="lhp-stat-label">每素材平均标签</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.quality_metrics.total_tag_results }}</div>
              <div class="lhp-stat-label">总标签结果</div>
            </div>
          </div>

          <!-- Confidence band chart -->
          <div class="lhp-subsection">
            <div class="lhp-subsection-title">置信度分布</div>
            <div class="lhp-confidence-bars" v-if="totalConfidence > 0">
              <div class="lhp-conf-row">
                <span class="lhp-conf-label">高置信</span>
                <div class="lhp-conf-bar-track">
                  <div class="lhp-conf-bar high" :style="{ width: confPct('high') + '%' }"></div>
                </div>
                <span class="lhp-conf-count">{{ health.quality_metrics.confidence_high }} ({{ confPct('high') }}%)</span>
              </div>
              <div class="lhp-conf-row">
                <span class="lhp-conf-label">中置信</span>
                <div class="lhp-conf-bar-track">
                  <div class="lhp-conf-bar medium" :style="{ width: confPct('medium') + '%' }"></div>
                </div>
                <span class="lhp-conf-count">{{ health.quality_metrics.confidence_medium }} ({{ confPct('medium') }}%)</span>
              </div>
              <div class="lhp-conf-row">
                <span class="lhp-conf-label">低置信</span>
                <div class="lhp-conf-bar-track">
                  <div class="lhp-conf-bar low" :style="{ width: confPct('low') + '%' }"></div>
                </div>
                <span class="lhp-conf-count">{{ health.quality_metrics.confidence_low }} ({{ confPct('low') }}%)</span>
              </div>
            </div>
            <div v-else class="lhp-empty">暂无置信度数据</div>
          </div>

          <!-- Feedback stats -->
          <div class="lhp-subsection" v-if="health.feedback_stats">
            <div class="lhp-subsection-title">用户反馈</div>
            <div class="lhp-stats-grid small">
              <div class="lhp-stat-card">
                <div class="lhp-stat-value">{{ health.feedback_stats.user_confirmed_tags }}</div>
                <div class="lhp-stat-label">已确认</div>
              </div>
              <div class="lhp-stat-card">
                <div class="lhp-stat-value">{{ health.feedback_stats.user_rejected_tags }}</div>
                <div class="lhp-stat-label">已拒绝</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Pipeline health -->
        <div v-else-if="activeTab === 'pipeline'" class="lhp-section">
          <div class="lhp-stats-grid">
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ candidatesPending }}</div>
              <div class="lhp-stat-label">候选词待审</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ candidatesApproved }}</div>
              <div class="lhp-stat-label">已通过</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.pipeline_health.stopword_count }}</div>
              <div class="lhp-stat-label">停用词</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.pipeline_health.total_aliases }}</div>
              <div class="lhp-stat-label">总别名数</div>
            </div>
            <div class="lhp-stat-card accent">
              <div class="lhp-stat-value">{{ health.pipeline_health.learned_aliases }}</div>
              <div class="lhp-stat-label">学习别名</div>
            </div>
            <div class="lhp-stat-card accent">
              <div class="lhp-stat-value">{{ health.pipeline_health.learned_tags }}</div>
              <div class="lhp-stat-label">学习标签</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.pipeline_health.custom_tags_active }}</div>
              <div class="lhp-stat-label">自定义标签</div>
            </div>
            <div class="lhp-stat-card">
              <div class="lhp-stat-value">{{ health.pipeline_health.composite_rules_active }}</div>
              <div class="lhp-stat-label">复合规则</div>
            </div>
          </div>

          <!-- Evidence source distribution -->
          <div class="lhp-subsection" v-if="Object.keys(health.evidence_by_source).length > 0">
            <div class="lhp-subsection-title">证据来源分布</div>
            <div class="lhp-list">
              <div
                v-for="(cnt, kind) in health.evidence_by_source"
                :key="kind"
                class="lhp-evidence-row"
              >
                <span class="lhp-ev-kind">{{ sourceKindLabel(kind) }}</span>
                <div class="lhp-mini-bar-track">
                  <div
                    class="lhp-mini-bar-fill ev"
                    :style="{ width: evidencePct(cnt) + '%' }"
                  ></div>
                </div>
                <span class="lhp-ev-count">{{ cnt }}</span>
              </div>
            </div>
          </div>

          <!-- Weakest assets -->
          <div class="lhp-subsection" v-if="health.weakest_assets.length > 0">
            <div class="lhp-subsection-title">标签最弱素材</div>
            <div class="lhp-list">
              <div v-for="a in health.weakest_assets.slice(0, 5)" :key="a.uid" class="lhp-weak-row">
                <span class="lhp-weak-name" :title="a.filename">{{ truncateFilename(a.filename) }}</span>
                <span class="lhp-weak-tags">{{ a.tag_count }}标签</span>
                <span class="lhp-weak-score">{{ a.avg_score.toFixed(2) }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useApiStore } from '../../stores/api.js'

const api = useApiStore()
const expanded = ref(false)
const loading = ref(false)
const health = ref(null)
const activeTab = ref('coverage')

const tabs = [
  { key: 'coverage', label: '覆盖率' },
  { key: 'distribution', label: '分布' },
  { key: 'quality', label: '质量' },
  { key: 'pipeline', label: '管道' },
]

const SLOT_LABELS = {
  object: '物体',
  place: '地点',
  scene: '场景',
  action: '动作',
  person: '人物',
  event: '事件',
  mood: '氛围',
  style: '风格',
  weather: '天气',
  season: '季节',
  nature: '自然',
  food: '美食',
  animal: '动物',
  indoor_outdoor: '室内外',
  time_of_day: '时段',
  shot_type: '镜头',
}

const SOURCE_KIND_LABELS = {
  llm: 'LLM',
  vision_object: '视觉-物体',
  vision_scene: '视觉-场景',
  vision_action: '视觉-动作',
  ocr: 'OCR',
  asr: 'ASR',
  gps: 'GPS',
  exif: 'EXIF',
  metadata: '元数据',
  rule: '规则',
  user: '用户',
}

function slotLabel(slot) {
  return SLOT_LABELS[slot] || slot
}

function sourceKindLabel(kind) {
  return SOURCE_KIND_LABELS[kind] || kind
}

function truncateFilename(name) {
  if (!name) return ''
  return name.length > 24 ? name.slice(0, 21) + '...' : name
}

const totalConfidence = computed(() => {
  if (!health.value) return 0
  const q = health.value.quality_metrics
  return q.confidence_high + q.confidence_medium + q.confidence_low
})

function confPct(band) {
  if (!health.value || totalConfidence.value === 0) return 0
  const q = health.value.quality_metrics
  const map = { high: q.confidence_high, medium: q.confidence_medium, low: q.confidence_low }
  return Math.round((map[band] / totalConfidence.value) * 100)
}

const maxEvidence = computed(() => {
  if (!health.value) return 1
  const vals = Object.values(health.value.evidence_by_source)
  return Math.max(...vals, 1)
})

function evidencePct(cnt) {
  return Math.round((cnt / maxEvidence.value) * 100)
}

const candidatesPending = computed(() => {
  if (!health.value) return 0
  return health.value.pipeline_health.candidates.pending || 0
})

const candidatesApproved = computed(() => {
  if (!health.value) return 0
  return health.value.pipeline_health.candidates.approved || 0
})

const thumbLoading = ref(false)
const thumbProgress = ref(0)
const thumbResult = ref(null)

// Round-14: track the thumbnail-generation poll so onBeforeUnmount can
// stop it. Previously navigating away from the library view left the
// 2s interval hitting /api/jobs/* until the job finished.
let _thumbPoll = null

async function generateThumbnails() {
  thumbLoading.value = true
  thumbProgress.value = 0
  thumbResult.value = null
  try {
    const resp = await api.api('POST', '/api/library/thumbnails/generate')
    const jobId = resp?.job_id
    if (!jobId) { thumbLoading.value = false; return }
    _thumbPoll = setInterval(async () => {
      try {
        const job = await api.api('GET', `/api/jobs/${jobId}`)
        thumbProgress.value = job.progress || 0
        if (job.status === 'done' || job.status === 'error') {
          clearInterval(_thumbPoll)
          _thumbPoll = null
          thumbLoading.value = false
          thumbResult.value = job.result || null
        }
      } catch {
        clearInterval(_thumbPoll)
        _thumbPoll = null
        thumbLoading.value = false
      }
    }, 2000)
  } catch {
    thumbLoading.value = false
  }
}

async function loadHealth() {
  loading.value = true
  try {
    const resp = await api.api('GET', '/api/library/health')
    health.value = resp
  } catch (e) {
    console.warn('Failed to load library health:', e)
  } finally {
    loading.value = false
  }
}

function toggle() {
  expanded.value = !expanded.value
}

watch(expanded, (val) => {
  if (val && !health.value) {
    loadHealth()
  }
})

// Round-14: stop the thumbnail-generation interval on unmount.
onBeforeUnmount(() => {
  if (_thumbPoll) {
    clearInterval(_thumbPoll)
    _thumbPoll = null
  }
})
</script>

<style scoped>
.lhp-panel {
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
}

.lhp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(255,255,255,0.03);
  cursor: pointer;
  user-select: none;
}

.lhp-header:hover {
  background: rgba(255,255,255,0.05);
}

.lhp-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
}

.lhp-toggle {
  font-size: 10px;
  color: var(--muted);
}

.lhp-body {
  padding: 8px 12px 12px;
}

.lhp-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
}

.lhp-tab {
  background: none;
  border: 1px solid rgba(255,255,255,0.08);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.15s;
}

.lhp-tab:hover {
  background: rgba(255,255,255,0.04);
  color: var(--fg);
}

.lhp-tab.active {
  background: rgba(90, 141, 238, 0.12);
  color: var(--accent);
  font-weight: 600;
}

.lhp-section {
  max-height: 400px;
  overflow-y: auto;
}

.lhp-loading,
.lhp-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 12px 0;
  text-align: center;
}

/* Stats grid */
.lhp-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}

.lhp-stats-grid.small {
  grid-template-columns: repeat(2, 1fr);
}

.lhp-stat-card {
  background: rgba(255,255,255,0.03);
  border-radius: 6px;
  padding: 10px 8px;
  text-align: center;
}

.lhp-stat-card.accent {
  background: rgba(90, 141, 238, 0.08);
}

.lhp-stat-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--fg);
  line-height: 1.2;
}

.lhp-stat-label {
  font-size: 10px;
  color: var(--muted);
  margin-top: 2px;
}

/* Coverage bar */
.lhp-bar-section {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.lhp-bar-label {
  font-size: 11px;
  color: var(--muted);
  width: 60px;
  flex-shrink: 0;
}

.lhp-bar-track {
  flex: 1;
  height: 8px;
  background: rgba(255,255,255,0.06);
  border-radius: 4px;
  overflow: hidden;
}

.lhp-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #5a8dee, #7b61ff);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.lhp-bar-pct {
  font-size: 11px;
  color: var(--muted);
  width: 36px;
  text-align: right;
  flex-shrink: 0;
}

/* Distribution list */
.lhp-list {
  display: flex;
  flex-direction: column;
}

.lhp-dist-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.lhp-dist-row:last-child {
  border-bottom: none;
}

.lhp-slot-name {
  width: 48px;
  flex-shrink: 0;
  font-weight: 500;
  color: var(--fg);
}

.lhp-slot-tags {
  width: 44px;
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted);
}

.lhp-mini-bar-track {
  flex: 1;
  height: 5px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
  overflow: hidden;
}

.lhp-mini-bar-fill {
  height: 100%;
  background: #5a8dee;
  border-radius: 3px;
  transition: width 0.3s;
}

.lhp-mini-bar-fill.ev {
  background: #7b61ff;
}

.lhp-slot-pct {
  width: 32px;
  text-align: right;
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

.lhp-slot-count {
  width: 44px;
  text-align: right;
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

/* Subsection */
.lhp-subsection {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.06);
}

.lhp-subsection-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  margin-bottom: 8px;
}

/* Tag cloud */
.lhp-tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.lhp-tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--fg);
}

.lhp-tag-chip small {
  font-size: 9px;
  color: var(--muted);
  font-weight: 600;
}

/* Confidence bars */
.lhp-confidence-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lhp-conf-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lhp-conf-label {
  width: 48px;
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}

.lhp-conf-bar-track {
  flex: 1;
  height: 6px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
  overflow: hidden;
}

.lhp-conf-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}

.lhp-conf-bar.high {
  background: #4caf50;
}

.lhp-conf-bar.medium {
  background: #ff9800;
}

.lhp-conf-bar.low {
  background: #f44336;
}

.lhp-conf-count {
  font-size: 10px;
  color: var(--muted);
  width: 80px;
  text-align: right;
  flex-shrink: 0;
}

/* Evidence rows */
.lhp-evidence-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
}

.lhp-ev-kind {
  width: 72px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--fg);
}

.lhp-ev-count {
  width: 44px;
  text-align: right;
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

/* Weak assets */
.lhp-weak-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.lhp-weak-row:last-child {
  border-bottom: none;
}

.lhp-weak-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--fg);
  font-size: 11px;
}

.lhp-weak-tags {
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

.lhp-weak-score {
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
  width: 32px;
  text-align: right;
}

.lhp-thumb-result {
  font-size: 11px;
  color: var(--muted);
  margin-left: 8px;
}
</style>
