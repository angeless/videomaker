<template>
  <div>
    <h3>图片语义分析</h3>
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
      <button class="btn btn-primary btn-sm" @click="analyze" :disabled="!appStore.projectDir">分析</button>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">语义检索</div>
      <div class="form-row"><label>搜索</label><input v-model="input.query" class="form-input" placeholder="输入搜索词" @keyup.enter="search" /></div>
      <div class="form-row"><label>结果数</label><input v-model.number="input.limit" type="number" class="form-input" /></div>
      <button class="btn btn-sm" @click="search">检索</button>
    </div>

    <div v-if="analyzeResult" class="cap-section">
      <div class="cap-subtitle">分析结果</div>
      <pre class="result-pre">{{ JSON.stringify(analyzeResult, null, 2) }}</pre>
    </div>
    <div v-if="searchResult" class="cap-section">
      <div class="cap-subtitle">检索结果</div>
      <pre class="result-pre">{{ JSON.stringify(searchResult, null, 2) }}</pre>
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
  input_mode: 'inline', image_paths: '', retrieval_mode: 'hybrid',
  analyze_max_images: 1200, auto_ingest: false, query: '', limit: 30,
})
const analyzeResult = ref(null)
const searchResult = ref(null)

async function analyze() {
  const paths = input.image_paths.replace(/\n/g, ',').replace(/，/g, ',').split(',').map(x => x.trim()).filter(Boolean)
  const data = await apiStore.api('POST', '/api/capabilities/image_semantic/analyze', {
    input_mode: input.input_mode, image_paths: paths, retrieval_mode: input.retrieval_mode,
    max_images: Math.min(Math.max(input.analyze_max_images, 1), 8000), auto_ingest: input.auto_ingest,
  })
  if (data.error) { capStore.setMessage(`图片语义分析失败：${data.error}`, 'error'); return }
  analyzeResult.value = data.result || null
  capStore.setMessage(`图片语义分析完成：${data.result?.analyzed_count || 0} 个条目`, 'success')
}

async function search() {
  const data = await apiStore.api('POST', '/api/capabilities/image_semantic/search', {
    query: input.query, limit: input.limit, retrieval_mode: input.retrieval_mode,
  })
  if (data.error) { capStore.setMessage(`图片语义检索失败：${data.error}`, 'error'); return }
  searchResult.value = data.result || null
  capStore.setMessage(`图片语义检索完成：命中 ${data.result?.total_hits || 0} 条`, 'success')
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 90px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
</style>
