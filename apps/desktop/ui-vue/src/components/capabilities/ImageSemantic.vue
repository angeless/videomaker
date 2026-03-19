<template>
  <div>
    <h3>图片语义分析</h3>
    <div v-if="aiStatus && aiStatus.degraded" class="ai-status-warn">
      <strong>功能受限：</strong>{{ aiStatus.message || '部分 AI 能力不可用' }}
      <span v-if="!aiStatus.vision_available"> · 视觉分析不可用</span>
      <span v-if="!aiStatus.vector_available"> · 向量检索不可用（仅关键词检索可用）</span>
    </div>
    <div class="cap-section">
      <div class="form-row"><label>输入模式</label>
        <select v-model="input.input_mode" class="form-input"><option value="inline">内联</option><option value="project">项目</option></select>
      </div>
      <div v-if="input.input_mode === 'inline'" class="form-row">
        <label>图片路径</label><textarea v-model="input.image_paths" class="form-input" rows="3" placeholder="每行一个路径"></textarea>
      </div>
      <div class="form-row"><label>检索模式</label>
        <select v-model="input.retrieval_mode" class="form-input"><option value="hybrid">混合</option><option value="keyword">关键词</option><option value="vector">向量</option></select>
      </div>
      <div class="form-row"><label>最大分析数</label><input v-model.number="input.analyze_max_images" type="number" class="form-input" /></div>
      <div class="form-row"><label>自动入库</label><input type="checkbox" v-model="input.auto_ingest" /></div>
      <div class="form-row"><label>{{ L.panelHints.imageSemantic.analyzeObjects }}</label><input type="checkbox" v-model="input.analyze_objects" /></div>
      <div class="form-row"><label>{{ L.panelHints.imageSemantic.analyzeScene }}</label><input type="checkbox" v-model="input.analyze_scene" /></div>
      <div class="form-row"><label>{{ L.panelHints.imageSemantic.analyzeMood }}</label><input type="checkbox" v-model="input.analyze_mood" /></div>
      <button class="btn btn-primary btn-sm" @click="analyze" :disabled="!appStore.projectDir || loadingAnalyze">{{ loadingAnalyze ? '分析中…' : '分析' }}</button>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">语义检索</div>
      <div class="form-row"><label>搜索</label><input v-model="input.query" class="form-input" placeholder="输入搜索词" @keyup.enter="search" /></div>
      <div class="form-row"><label>结果数</label><input v-model.number="input.limit" type="number" class="form-input" /></div>
      <button class="btn btn-sm" @click="search" :disabled="loadingSearch">{{ loadingSearch ? '检索中…' : '检索' }}</button>
    </div>

    <div v-if="analyzeResult" class="cap-section">
      <ResultCard title="分析结果" status="success">
        <div class="analyze-summary">
          <span class="analyze-stat">已分析 <strong>{{ analyzeResult.analyzed_count || 0 }}</strong> 张</span>
          <span v-if="analyzeResult.skipped_count" class="analyze-stat">跳过 {{ analyzeResult.skipped_count }} 张</span>
        </div>
        <div v-if="analyzeResult.tags && analyzeResult.tags.length" class="tag-cloud">
          <span v-for="tag in analyzeResult.tags.slice(0, 50)" :key="tag.name || tag" class="tag-bubble">
            {{ tag.name || tag }}
            <span v-if="tag.count" class="tag-count">{{ tag.count }}</span>
          </span>
        </div>
        <div v-if="!analyzeResult.tags || analyzeResult.tags.length === 0" class="result-json-fallback">
          <pre>{{ JSON.stringify(analyzeResult, null, 2) }}</pre>
        </div>
      </ResultCard>
    </div>
    <div v-if="searchResult" class="cap-section">
      <ResultCard :title="`检索结果（${searchResult.total_hits || 0} 条）`" status="success">
        <div v-if="searchResult.results && searchResult.results.length" class="search-results">
          <div v-for="(item, i) in searchResult.results.slice(0, 30)" :key="i" class="search-item">
            <span class="search-rank">#{{ i + 1 }}</span>
            <span class="search-filename">{{ item.filename || item.path || item.asset_id }}</span>
            <span v-if="item.score != null" class="search-score">{{ (item.score * 100).toFixed(0) }}%</span>
            <div v-if="item.tags" class="search-tags">
              <span v-for="t in (Array.isArray(item.tags) ? item.tags : []).slice(0, 5)" :key="t" class="tag-bubble tag-sm">{{ t }}</span>
            </div>
          </div>
        </div>
        <div v-else class="result-json-fallback">
          <pre>{{ JSON.stringify(searchResult, null, 2) }}</pre>
        </div>
      </ResultCard>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import ResultCard from '../common/ResultCard.vue'
import labels from '../../i18n/labels.js'

const L = labels
const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const input = reactive({
  input_mode: 'inline', image_paths: '', retrieval_mode: 'hybrid',
  analyze_max_images: 1200, auto_ingest: false,
  analyze_objects: true, analyze_scene: true, analyze_mood: true,
  query: '', limit: 30,
})
const analyzeResult = ref(null)
const searchResult = ref(null)
const aiStatus = ref(null)
const loadingAnalyze = ref(false)
const loadingSearch = ref(false)

async function analyze() {
  if (!appStore.projectDir || loadingAnalyze.value) return
  loadingAnalyze.value = true
  try {
    const paths = input.image_paths.replace(/\n/g, ',').replace(/，/g, ',').split(',').map(x => x.trim()).filter(Boolean)
    const data = await apiStore.api('POST', '/api/capabilities/image_semantic/analyze', {
      input_mode: input.input_mode, image_paths: paths, retrieval_mode: input.retrieval_mode,
      max_images: Math.min(Math.max(input.analyze_max_images, 1), 8000), auto_ingest: input.auto_ingest,
    })
    if (data.error) { capStore.setMessage(`图片语义分析失败：${data.error}`, 'error'); return }
    analyzeResult.value = data.result || null
    if (data.ai_status) aiStatus.value = data.ai_status
    capStore.setMessage(`图片语义分析完成：${data.result?.analyzed_count || 0} 个条目`, 'success')
  } finally {
    loadingAnalyze.value = false
  }
}

async function search() {
  if (loadingSearch.value) return
  loadingSearch.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/image_semantic/search', {
      query: input.query, limit: input.limit, retrieval_mode: input.retrieval_mode,
    })
    if (data.error) { capStore.setMessage(`图片语义检索失败：${data.error}`, 'error'); return }
    searchResult.value = data.result || null
    if (data.ai_status) aiStatus.value = data.ai_status
    capStore.setMessage(`图片语义检索完成：命中 ${data.result?.total_hits || 0} 条`, 'success')
  } finally {
    loadingSearch.value = false
  }
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 90px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.ai-status-warn { background: rgba(255, 179, 0, 0.12); border: 1px solid rgba(255, 179, 0, 0.3); border-radius: 6px; padding: 10px 14px; font-size: 12px; color: #b88a00; margin-bottom: 16px; line-height: 1.6; }
.analyze-summary { margin-bottom: 12px; display: flex; gap: 16px; }
.analyze-stat { font-size: 13px; color: var(--muted); }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 6px; }
.tag-bubble { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 12px; background: rgba(90, 141, 238, 0.1); color: var(--accent); font-size: 12px; }
.tag-bubble .tag-count { font-size: 10px; color: var(--muted); }
.tag-sm { padding: 1px 6px; font-size: 10px; border-radius: 8px; }
.search-results { display: flex; flex-direction: column; gap: 6px; }
.search-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
.search-item:last-child { border-bottom: none; }
.search-rank { width: 28px; font-size: 11px; color: var(--muted); font-weight: 600; flex-shrink: 0; }
.search-filename { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-score { font-size: 12px; color: var(--accent); font-weight: 500; flex-shrink: 0; }
.search-tags { display: flex; gap: 3px; flex-shrink: 0; }
.result-json-fallback pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
</style>
