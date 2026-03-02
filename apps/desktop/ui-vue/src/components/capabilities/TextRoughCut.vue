<template>
  <div>
    <h3>文字粗剪</h3>
    <div class="cap-section">
      <div class="form-row"><label>去除口头词</label><input v-model="input.removed_phrases" class="form-input" placeholder="嗯,啊,然后,就是 (逗号分隔)" /></div>
      <div class="form-row"><label>目标时长(秒)</label><input v-model.number="input.target_duration_s" type="number" class="form-input" /></div>
      <div class="form-row"><label>合并间隔(秒)</label><input v-model.number="input.merge_gap_s" type="number" step="0.05" class="form-input" /></div>
      <div class="form-row"><label>保留句号</label><input v-model="input.keep_span_indexes" class="form-input" placeholder="如 1-5,8,10-12" /></div>
      <div class="form-row"><label>丢弃句号</label><input v-model="input.drop_span_indexes" class="form-input" placeholder="如 3,6-7" /></div>
      <div class="form-row">
        <label>自动去口头词</label>
        <input type="checkbox" v-model="input.apply_removed_phrases" />
      </div>
      <div class="btn-row">
        <button class="btn btn-sm" @click="loadSource" :disabled="!appStore.projectDir">加载字幕</button>
        <button class="btn btn-primary btn-sm" @click="buildPlan" :disabled="!appStore.projectDir">生成粗剪规划</button>
      </div>
    </div>

    <div v-if="spans.length" class="cap-section">
      <div class="cap-subtitle">
        字幕句子 ({{ spans.length }} 句, 保留 {{ spans.filter(s => s.keep).length }} 句)
      </div>
      <div class="form-row">
        <input v-model="filterKeyword" class="form-input" placeholder="过滤关键词" style="flex:1" />
      </div>
      <div class="btn-row" style="margin-bottom:8px">
        <button class="btn btn-xs" @click="setAll(true)">全选</button>
        <button class="btn btn-xs" @click="setAll(false)">全不选</button>
        <button class="btn btn-xs" @click="invertSel">反选</button>
        <button class="btn btn-xs" @click="removeFillers">去口头词</button>
      </div>
      <div class="span-list">
        <div v-for="span in filteredSpans" :key="span.index" class="span-item" :class="{ dropped: !span.keep }">
          <input type="checkbox" v-model="span.keep" @change="syncInputs" />
          <span class="span-index">#{{ span.index }}</span>
          <span class="span-text">{{ span.text }}</span>
          <span class="span-time text-muted">{{ Number(span.start || 0).toFixed(1) }}s</span>
        </div>
      </div>
    </div>

    <div v-if="plan" class="cap-section">
      <div class="cap-subtitle">粗剪规划</div>
      <pre class="result-pre">{{ JSON.stringify(plan, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import { useFormatters } from '../../composables/useFormatters.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()
const { parseSpanIndexExpr, formatSpanIndexExpr } = useFormatters()

const input = reactive({
  removed_phrases: '', target_duration_s: 15, merge_gap_s: 0.15,
  keep_span_indexes: '', drop_span_indexes: '', apply_removed_phrases: false,
})
const spans = ref([])
const plan = ref(null)
const filterKeyword = ref('')

const filteredSpans = computed(() => {
  const kw = filterKeyword.value.trim().toLowerCase()
  if (!kw) return spans.value
  return spans.value.filter(s => (s.text || '').toLowerCase().includes(kw))
})

function syncInputs() {
  const keep = [], drop = []
  for (const s of spans.value) {
    if (s.keep) keep.push(s.index); else drop.push(s.index)
  }
  if (keep.length === spans.value.length) { input.keep_span_indexes = ''; input.drop_span_indexes = ''; return }
  if (keep.length <= drop.length) { input.keep_span_indexes = formatSpanIndexExpr(keep); input.drop_span_indexes = '' }
  else { input.keep_span_indexes = ''; input.drop_span_indexes = formatSpanIndexExpr(drop) }
}

function setAll(keep) { spans.value.forEach(s => s.keep = keep); syncInputs() }
function invertSel() { spans.value.forEach(s => s.keep = !s.keep); syncInputs() }

function removeFillers() {
  const phrases = input.removed_phrases.replace(/，/g, ',').split(',').map(x => x.trim().toLowerCase()).filter(Boolean)
  if (!phrases.length) { capStore.setMessage('请先填写去除口头词', 'warning'); return }
  let hit = 0
  spans.value.forEach(s => {
    const text = (s.text || '').toLowerCase()
    if (phrases.some(p => text.includes(p))) { s.keep = false; hit++ }
  })
  syncInputs()
  capStore.setMessage(`已批量取消 ${hit} 句口头词相关句子`, 'info')
}

async function loadSource() {
  if (!appStore.projectDir) return
  const data = await apiStore.api('GET', '/api/capabilities/text_rough_cut/source')
  if (data.error) { capStore.setMessage(`字幕加载失败：${data.error}`, 'error'); return }
  const raw = Array.isArray(data.spans) ? data.spans : []
  const keepSet = new Set(parseSpanIndexExpr(input.keep_span_indexes, raw.length))
  const dropSet = new Set(parseSpanIndexExpr(input.drop_span_indexes, raw.length))
  const hasManual = keepSet.size > 0 || dropSet.size > 0
  spans.value = raw.map(s => {
    let keep = true
    if (hasManual) {
      if (keepSet.size > 0 && !keepSet.has(s.index)) keep = false
      if (dropSet.has(s.index)) keep = false
    }
    return { ...s, keep }
  })
}

async function buildPlan() {
  if (!appStore.projectDir) return
  const payload = {
    removed_phrases: input.removed_phrases, target_duration_s: input.target_duration_s,
    merge_gap_s: input.merge_gap_s, keep_span_indexes: input.keep_span_indexes,
    drop_span_indexes: input.drop_span_indexes, apply_removed_phrases: input.apply_removed_phrases,
  }
  const data = await apiStore.api('POST', '/api/capabilities/text_rough_cut/plan', payload)
  if (data.error) { capStore.setMessage(`文字粗剪规划失败：${data.error}`, 'error'); return }
  plan.value = data.plan || null
  const decisions = plan.value?.decisions || []
  if (decisions.length && spans.value.length) {
    const keepByIdx = new Map(decisions.map(d => [d.index, !!d.kept]))
    spans.value.forEach(s => { if (keepByIdx.has(s.index)) s.keep = keepByIdx.get(s.index) })
    syncInputs()
  }
  capStore.setMessage(`已生成文字粗剪规划：保留 ${plan.value?.kept_span_count || 0}/${plan.value?.total_span_count || 0} 句`, 'success')
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 110px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 6px; margin-top: 8px; }
.btn-xs { font-size: 11px; padding: 2px 8px; }
.span-list { max-height: 400px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; }
.span-item { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-bottom: 1px solid var(--border); font-size: 12px; }
.span-item.dropped { opacity: 0.4; text-decoration: line-through; }
.span-index { color: var(--muted); width: 32px; flex-shrink: 0; }
.span-text { flex: 1; }
.span-time { font-size: 11px; flex-shrink: 0; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
</style>
