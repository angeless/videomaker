<template>
  <div>
    <h3>字幕校准</h3>
    <div class="cap-section">
      <div class="form-row"><label>输入模式</label>
        <select v-model="input.input_mode" class="form-input"><option value="project">项目</option><option value="inline">内联</option></select>
      </div>
      <div class="form-row"><label>模式</label>
        <select v-model="input.mode" class="form-input"><option value="timeline_align">时间轴对齐</option></select>
      </div>
      <div class="form-row"><label>翻译</label>
        <select v-model="input.translation" class="form-input"><option value="off">关闭</option><option value="on">开启</option></select>
      </div>
      <div class="form-row"><label>源音频</label><input v-model="input.source_audio" class="form-input" placeholder="留空使用项目默认" /></div>
      <div class="form-row"><label>启用 AI 辅助</label><input type="checkbox" v-model="input.use_llm" /></div>
      <div v-if="input.use_llm">
        <div class="form-row"><label>AI 服务商</label><input v-model="input.llm_provider" class="form-input" /></div>
        <div class="form-row"><label>AI 模型</label><input v-model="input.llm_model" class="form-input" /></div>
      </div>
      <div v-if="input.input_mode === 'inline'" class="form-row">
        <label>字幕 JSON</label><textarea v-model="input.subtitles_json" class="form-input" rows="4" placeholder='[{"start":0,"end":1,"text":"..."}]'></textarea>
      </div>
      <div class="btn-row">
        <button class="btn btn-sm" @click="plan" :disabled="!appStore.projectDir || loadingPlan">{{ loadingPlan ? '规划中…' : '生成规划' }}</button>
        <button class="btn btn-primary btn-sm" @click="run" :disabled="!appStore.projectDir || loadingRun">{{ loadingRun ? '校准中…' : '执行校准' }}</button>
      </div>
    </div>
    <div v-if="planResult" class="cap-section">
      <div class="cap-subtitle">规划结果</div>
      <div v-if="planResult.subtitle_count != null" class="stat-row">
        <span class="stat-item">字幕总数 <strong>{{ planResult.subtitle_count }}</strong></span>
        <span v-if="planResult.overlap_count" class="stat-item">重叠 <strong>{{ planResult.overlap_count }}</strong></span>
        <span v-if="planResult.gap_issues" class="stat-item">间隔问题 <strong>{{ planResult.gap_issues }}</strong></span>
      </div>
      <details><summary class="detail-summary">查看完整规划</summary><pre class="result-pre">{{ JSON.stringify(planResult, null, 2) }}</pre></details>
    </div>
    <div v-if="runResult" class="cap-section">
      <div class="cap-subtitle">执行结果</div>
      <!-- Quality report -->
      <div v-if="runResult.quality_report" class="stat-row">
        <span class="stat-item">总数 <strong>{{ runResult.quality_report.total_subtitles || 0 }}</strong></span>
        <span class="stat-item">时间轴调整 <strong>{{ runResult.quality_report.timeline_changed_count || 0 }}</strong></span>
        <span v-if="runResult.quality_report.text_changed_count" class="stat-item">文本修改 <strong>{{ runResult.quality_report.text_changed_count }}</strong></span>
        <span v-if="runResult.quality_report.translation_count" class="stat-item">翻译 <strong>{{ runResult.quality_report.translation_count }}</strong></span>
      </div>
      <!-- Timeline changes -->
      <div v-if="runResult.timeline_changes && runResult.timeline_changes.length" style="margin-top:8px">
        <details>
          <summary class="detail-summary">时间轴变更 ({{ runResult.timeline_changes.length }})</summary>
          <div class="change-list">
            <div v-for="(ch, i) in runResult.timeline_changes" :key="i" class="change-item">
              #{{ ch.index ?? i }} {{ Number(ch.old_start || 0).toFixed(2) }}s→{{ Number(ch.new_start || 0).toFixed(2) }}s {{ ch.reason || '' }}
            </div>
          </div>
        </details>
      </div>
      <!-- Calibrated subtitles -->
      <div v-if="runResult.calibrated_subtitles && runResult.calibrated_subtitles.length" style="margin-top:8px">
        <details>
          <summary class="detail-summary">校准后字幕 ({{ runResult.calibrated_subtitles.length }})</summary>
          <div class="sub-list">
            <div v-for="(s, i) in runResult.calibrated_subtitles" :key="i" class="sub-item">
              <span class="sub-time">{{ Number(s.start || 0).toFixed(2) }}–{{ Number(s.end || 0).toFixed(2) }}s</span>
              <span class="sub-text">{{ s.text }}</span>
            </div>
          </div>
        </details>
      </div>
      <details style="margin-top:8px"><summary class="detail-summary">查看完整 JSON</summary><pre class="result-pre">{{ JSON.stringify(runResult, null, 2) }}</pre></details>
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

const input = reactive({
  input_mode: 'project', mode: 'timeline_align', translation: 'off',
  source_audio: '', use_llm: false, llm_provider: '', llm_model: '', subtitles_json: '',
})
const planResult = ref(null)
const runResult = ref(null)
const loadingPlan = ref(false)
const loadingRun = ref(false)

function buildPayload() {
  const p = {
    input_mode: input.input_mode, mode: input.mode, translation: input.translation,
    source_audio: input.source_audio,
  }
  if (input.input_mode === 'inline') {
    try { p.subtitles = JSON.parse(input.subtitles_json) } catch { capStore.setMessage('字幕 JSON 格式错误', 'error'); return null }
  }
  return p
}

async function plan() {
  if (loadingPlan.value) return
  loadingPlan.value = true
  try {
    const p = buildPayload(); if (!p) return
    const data = await apiStore.api('POST', '/api/capabilities/subtitle_calibration/plan', p)
    if (data.error) { capStore.setMessage(`字幕校准规划失败：${data.error}`, 'error'); return }
    planResult.value = data.plan || null
    capStore.setMessage('已生成字幕校准规划', 'success')
  } finally {
    loadingPlan.value = false
  }
}

async function run() {
  if (loadingRun.value) return
  loadingRun.value = true
  try {
    const p = buildPayload(); if (!p) return
    p.use_llm = input.use_llm; p.llm_provider = input.llm_provider; p.llm_model = input.llm_model
    const data = await apiStore.api('POST', '/api/capabilities/subtitle_calibration/run', p)
    if (data.error) { capStore.setMessage(`字幕校准失败：${data.error}`, 'error'); return }
    runResult.value = data.result || null
    const report = runResult.value?.quality_report || {}
    capStore.setMessage(`字幕校准完成：共 ${report.total_subtitles || 0} 条，时间轴调整 ${report.timeline_changed_count || 0} 条`, 'success')
  } finally {
    loadingRun.value = false
  }
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 90px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 8px; margin-top: 8px; }
.stat-row { display: flex; flex-wrap: wrap; gap: 14px; padding: 10px 14px; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }
.stat-item { font-size: 12px; }
.stat-item strong { color: var(--accent); }
.detail-summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.change-list, .sub-list { max-height: 250px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; margin-top: 4px; }
.change-item, .sub-item { font-size: 11px; padding: 3px 8px; border-bottom: 1px solid var(--border); }
.sub-time { color: var(--muted); margin-right: 8px; }
.sub-text { color: var(--text); }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
</style>
