<template>
  <div v-if="visible" class="evidence-overlay" @click.self="close">
    <div class="evidence-panel">
      <div class="evidence-header">
        <span class="evidence-title">标签解释</span>
        <span class="evidence-asset">{{ assetFilename }}</span>
        <button class="btn btn-ghost evidence-close" @click="close">✕</button>
      </div>

      <div v-if="loading" class="evidence-loading">加载中...</div>

      <div v-else-if="error" class="evidence-error">{{ error }}</div>

      <div v-else class="evidence-body">
        <!-- Tag results -->
        <div v-if="tagResults.length > 0" class="evidence-section">
          <div class="section-label">命中标签</div>
          <div v-for="tr in tagResults" :key="tr.tag_id" class="tag-result-row">
            <span class="tr-name">{{ tr.tag_name }}</span>
            <span class="tr-band" :class="`band-${tr.confidence_band}`">{{ tr.confidence_band }}</span>
            <span class="tr-score">{{ (tr.effective_score * 100).toFixed(0) }}分</span>
            <div v-if="tr.score_breakdown" class="score-breakdown">
              <span class="sb-item">
                基础 {{ (tr.score_breakdown.base_score * 100).toFixed(0) }}
              </span>
              <span v-if="tr.score_breakdown.user_adjustment !== 0" class="sb-item sb-adj">
                {{ tr.score_breakdown.user_adjustment > 0 ? '+' : '' }}{{ (tr.score_breakdown.user_adjustment * 100).toFixed(0) }}调整
              </span>
            </div>
          </div>
        </div>

        <!-- Evidence list -->
        <div v-if="evidenceList.length > 0" class="evidence-section">
          <div class="section-label">证据来源</div>
          <div v-for="(ev, idx) in evidenceList" :key="idx" class="evidence-row">
            <span class="ev-slot">{{ ev.semantic_slot }}</span>
            <span class="ev-kind" :class="`kind-${ev.source_kind}`">{{ kindLabel(ev.source_kind) }}</span>
            <span class="ev-value">{{ ev.raw_value }}</span>
            <span class="ev-score">{{ (ev.weighted_score * 100).toFixed(0) }}分</span>
          </div>
        </div>

        <!-- P5-D: Per-tag feedback actions -->
        <div v-if="tagResults.length > 0" class="evidence-section">
          <div class="section-label">标签反馈</div>
          <div v-for="tr in tagResults" :key="'fb-' + tr.tag_id" class="feedback-row">
            <FeedbackActions
              :asset-id="props.assetId"
              :tag-id="tr.tag_id"
              :tag-name="tr.tag_name"
              :confirm-state="tr.user_confirm_state || 'none'"
              @feedback-done="onFeedbackDone"
            />
          </div>
        </div>

        <!-- P5-D: Add missing tag -->
        <div class="evidence-section">
          <div class="section-label">添加缺失标签</div>
          <FeedbackActions
            :asset-id="props.assetId"
            @feedback-done="onFeedbackDone"
          />
        </div>

        <div v-if="tagResults.length === 0 && evidenceList.length === 0" class="evidence-empty">
          暂无详细解释信息
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useApiStore } from '../../stores/api.js'
import FeedbackActions from './FeedbackActions.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  assetId: { type: String, default: '' },
  assetFilename: { type: String, default: '' },
  tagId: { type: [Number, String, null], default: null },
})

const emit = defineEmits(['close', 'feedback-done'])

const api = useApiStore()
const loading = ref(false)
const error = ref('')
const tagResults = ref([])
const evidenceList = ref([])

function kindLabel(kind) {
  const map = {
    llm: 'AI分析',
    clip: 'CLIP',
    ocr: '文字识别',
    face: '人脸',
    gps: '地理',
    user: '用户',
    filename: '文件名',
    test_model: '测试',
  }
  return map[kind] || kind
}

async function fetchEvidence() {
  if (!props.assetId) return
  loading.value = true
  error.value = ''
  tagResults.value = []
  evidenceList.value = []

  const params = new URLSearchParams({ asset_id: props.assetId })
  if (props.tagId != null) {
    params.set('tag_id', String(props.tagId))
  }
  const data = await api.api('GET', `/api/library/evidence?${params}`)
  loading.value = false

  if (data.error) {
    error.value = data.error
    return
  }
  tagResults.value = data.tag_results || []
  evidenceList.value = data.evidence_list || []
}

function close() {
  emit('close')
}

function onFeedbackDone(detail) {
  // Re-fetch evidence to reflect updated scores/states
  fetchEvidence()
  // Propagate to parent so search results can refresh
  emit('feedback-done', detail)
}

watch(() => props.visible, (val) => {
  if (val && props.assetId) {
    fetchEvidence()
  }
})
</script>

<style scoped>
.evidence-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.evidence-panel {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  width: 480px;
  max-height: 70vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.evidence-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.evidence-title {
  font-weight: 600;
  font-size: 14px;
}

.evidence-asset {
  font-size: 12px;
  color: var(--muted);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.evidence-close {
  font-size: 16px;
  padding: 2px 8px;
  flex-shrink: 0;
}

.evidence-body {
  padding: 12px 16px;
}

.evidence-loading,
.evidence-error,
.evidence-empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.evidence-error {
  color: var(--text-danger, #f44336);
}

.evidence-section {
  margin-bottom: 16px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.tag-result-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  flex-wrap: wrap;
}

.tr-name {
  font-weight: 500;
  font-size: 13px;
}

.tr-band {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}

.band-high { background: rgba(76, 175, 80, 0.15); color: #4caf50; }
.band-medium { background: rgba(255, 183, 77, 0.18); color: #ffb74d; }
.band-low { background: rgba(239, 83, 80, 0.15); color: #ef5350; }

.tr-score {
  font-size: 12px;
  color: var(--accent);
  margin-left: auto;
}

.score-breakdown {
  width: 100%;
  display: flex;
  gap: 8px;
  padding-left: 4px;
}

.sb-item {
  font-size: 10px;
  color: var(--muted);
}

.sb-adj {
  color: #ffb74d;
}

.evidence-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  font-size: 12px;
}

.ev-slot {
  font-weight: 500;
  min-width: 50px;
}

.ev-kind {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.kind-llm { background: rgba(90, 141, 238, 0.15); color: var(--accent); }
.kind-clip { background: rgba(171, 71, 188, 0.15); color: #ab47bc; }
.kind-ocr { background: rgba(255, 183, 77, 0.18); color: #ffb74d; }
.kind-user { background: rgba(76, 175, 80, 0.15); color: #4caf50; }
.kind-gps { background: rgba(0, 188, 212, 0.15); color: #00bcd4; }

.ev-value {
  flex: 1;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ev-score {
  color: var(--accent);
  flex-shrink: 0;
}

.feedback-row {
  padding: 4px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.feedback-row:last-child {
  border-bottom: none;
}
</style>
