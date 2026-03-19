<template>
  <div>
    <h3>短视频快剪</h3>

    <!-- 参数区 -->
    <div class="cap-section">
      <div class="form-row"><label>目标时长(秒)</label><input v-model.number="input.target_duration_s" type="number" min="1" max="600" class="form-input" /></div>
      <div class="form-row"><label>最大片段数</label><input v-model.number="input.max_clips" type="number" min="1" max="50" class="form-input" /></div>
      <div class="form-row"><label>最小间隔(秒)</label><input v-model.number="input.min_gap_s" type="number" min="0" max="5" step="0.1" class="form-input" /></div>
      <div class="btn-row">
        <button class="btn btn-sm" @click="loadCandidates" :disabled="!appStore.projectDir || loadingCandidates">{{ loadingCandidates ? '加载中…' : '加载候选片段' }}</button>
        <button class="btn btn-primary btn-sm" @click="buildPlan" :disabled="!appStore.projectDir || loading">{{ loading ? '生成中…' : '生成快剪规划' }}</button>
      </div>
      <div v-if="!candidates.length && appStore.projectDir && !loadingCandidates" class="form-hint">点击「加载候选片段」从脚本自动提取高光片段，或直接点击「生成快剪规划」由后端自动读取项目脚本</div>
    </div>

    <!-- 候选片段列表 -->
    <div v-if="candidates.length" class="cap-section">
      <div class="cap-subtitle">候选片段 ({{ candidates.length }} 段)</div>
      <div class="candidate-list">
        <div v-for="(c, i) in candidates" :key="i" class="candidate-item">
          <input type="checkbox" v-model="c.selected" />
          <span class="cand-index">#{{ i + 1 }}</span>
          <span class="cand-time">{{ Number(c.start).toFixed(1) }}s – {{ Number(c.end).toFixed(1) }}s</span>
          <span class="cand-dur text-muted">({{ (c.end - c.start).toFixed(1) }}s)</span>
          <span class="cand-score">{{ (c.score * 100).toFixed(0) }}分</span>
          <span v-if="c.reason" class="cand-reason text-muted">{{ c.reason }}</span>
        </div>
      </div>
    </div>

    <!-- 规划结果 -->
    <div v-if="plan" class="cap-section">
      <div class="cap-subtitle">快剪规划</div>
      <div v-if="!plan.clips || plan.clips.length === 0" class="plan-empty">
        <div class="plan-empty-icon">⚡</div>
        <div class="plan-empty-text">未选中任何高光片段</div>
      </div>
      <div v-else class="plan-summary">
        <div class="plan-stat">选中 <strong>{{ plan.clips.length }}</strong> 个片段</div>
        <div class="plan-stat">总时长 <strong>{{ Number(plan.total_duration_s).toFixed(1) }}s</strong></div>
        <div class="clip-list">
          <div v-for="(clip, i) in plan.clips" :key="i" class="clip-item">
            <span class="clip-index">#{{ i + 1 }}</span>
            <span class="clip-time">{{ Number(clip.start).toFixed(1) }}s – {{ Number(clip.end).toFixed(1) }}s</span>
            <span class="clip-dur">({{ (clip.end - clip.start).toFixed(1) }}s)</span>
            <span class="clip-score">{{ (clip.score * 100).toFixed(0) }}分</span>
            <span v-if="clip.reason" class="clip-reason text-muted">{{ clip.reason }}</span>
          </div>
        </div>
        <details class="plan-raw">
          <summary>查看完整规划</summary>
          <pre class="result-pre">{{ JSON.stringify(plan, null, 2) }}</pre>
        </details>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const input = reactive({ target_duration_s: 30, max_clips: 8, min_gap_s: 0.3 })
const candidates = ref([])
const plan = ref(null)
const loading = ref(false)
const loadingCandidates = ref(false)

async function loadCandidates() {
  if (!appStore.projectDir || loadingCandidates.value) return
  loadingCandidates.value = true
  try {
    // Read script to extract candidate clips
    const data = await apiStore.api('GET', '/api/capabilities/text_rough_cut/source')
    if (data.error) { capStore.setMessage(`加载失败：${data.error}`, 'error'); return }
    const spans = Array.isArray(data.spans) ? data.spans : []
    if (!spans.length) { capStore.setMessage('暂无字幕/脚本数据，请先完成素材分析', 'warning'); return }
    let cursor = 0
    candidates.value = spans.map((s, i) => {
      const start = typeof s.start === 'number' ? s.start : cursor
      const end = typeof s.end === 'number' ? s.end : start + 3
      cursor = end
      return {
        start, end,
        score: 0.5 + (i === 0 ? 0.12 : 0),
        reason: (s.text || '').slice(0, 40),
        selected: true,
      }
    })
    capStore.setMessage(`已加载 ${candidates.value.length} 个候选片段`, 'info')
  } finally {
    loadingCandidates.value = false
  }
}

async function buildPlan() {
  if (!appStore.projectDir || loading.value) return
  loading.value = true
  try {
    const payload = {
      target_duration_s: input.target_duration_s,
      max_clips: input.max_clips,
    }
    // If user loaded and filtered candidates, send only selected ones
    if (candidates.value.length > 0) {
      payload.candidates = candidates.value
        .filter(c => c.selected)
        .map(c => ({ start: c.start, end: c.end, score: c.score, reason: c.reason }))
    }
    const data = await apiStore.api('POST', '/api/capabilities/short_clip/plan', payload)
    if (data.error) { capStore.setMessage(`快剪规划失败：${data.error}`, 'error'); return }
    plan.value = data.plan || null
    const clipCount = plan.value?.clips?.length || 0
    const totalDur = Number(plan.value?.total_duration_s || 0).toFixed(1)
    capStore.setMessage(`已生成快剪规划：${clipCount} 个片段，共 ${totalDur}s`, 'success')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 110px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 6px; margin-top: 8px; }
.form-hint { font-size: 11px; color: var(--muted); margin-top: 6px; }

/* Candidate list */
.candidate-list { max-height: 300px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; }
.candidate-item { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-bottom: 1px solid var(--border); font-size: 12px; }
.cand-index { color: var(--muted); width: 28px; flex-shrink: 0; }
.cand-time { flex-shrink: 0; }
.cand-dur { flex-shrink: 0; font-size: 11px; }
.cand-score { flex-shrink: 0; color: var(--accent); font-weight: 600; }
.cand-reason { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }

/* Plan result */
.plan-empty { text-align: center; padding: 24px; color: var(--muted); }
.plan-empty-icon { font-size: 32px; margin-bottom: 8px; opacity: 0.4; }
.plan-empty-text { font-size: 13px; }
.plan-summary { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.plan-stat { font-size: 13px; margin-bottom: 4px; }
.plan-stat strong { color: var(--accent); }
.clip-list { margin-top: 8px; border: 1px solid var(--border); border-radius: 6px; }
.clip-item { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-bottom: 1px solid var(--border); font-size: 12px; }
.clip-item:last-child { border-bottom: none; }
.clip-index { color: var(--muted); width: 28px; flex-shrink: 0; }
.clip-time { flex-shrink: 0; }
.clip-dur { flex-shrink: 0; font-size: 11px; color: var(--muted); }
.clip-score { flex-shrink: 0; color: var(--accent); font-weight: 600; }
.clip-reason { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.plan-raw { margin-top: 8px; }
.plan-raw summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
</style>
