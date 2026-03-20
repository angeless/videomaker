<template>
  <div>
    <h3>公众号扩写</h3>
    <div class="cap-section">
      <div class="form-row"><label>源文本</label><textarea v-model="input.source_text" class="form-input" rows="4" placeholder="粘贴原始文案"></textarea></div>
      <div class="form-row"><label>要点</label><input v-model="input.key_points" class="form-input" placeholder="逗号分隔关键点" /></div>
      <div class="form-row"><label>语气</label>
        <select v-model="input.tone" class="form-input"><option value="professional">专业</option><option value="casual">轻松</option><option value="humorous">幽默</option></select>
      </div>
      <div class="form-row"><label>目标字数</label><input v-model.number="input.length_target" type="number" class="form-input" :placeholder="L.panelHints.articleExpand.lengthTargetPlaceholder" /></div>
      <div class="form-row"><label>标题数量</label><input v-model.number="input.title_count" type="number" class="form-input" /></div>
      <div class="form-row"><label>启用 AI 辅助</label><input type="checkbox" v-model="input.use_llm" /></div>
      <button class="btn btn-primary btn-sm" @click="generate" :disabled="!canGenerate || loading">{{ loading ? '生成中…' : '生成扩写' }}</button>
      <div v-if="!input.source_text.trim() && appStore.projectDir" class="form-hint">请先粘贴源文本</div>
    </div>
    <div v-if="result" class="cap-section">
      <div class="cap-subtitle">扩写结果</div>
      <!-- 候选标题 -->
      <div v-if="result.title_candidates && result.title_candidates.length" class="result-block">
        <div class="block-label">候选标题</div>
        <div v-for="(t, i) in result.title_candidates" :key="i" class="title-candidate">{{ i + 1 }}. {{ t }}</div>
      </div>
      <!-- 导语 -->
      <div v-if="result.lead" class="result-block">
        <div class="block-label">导语</div>
        <div class="block-text">{{ result.lead }}</div>
      </div>
      <!-- 章节 -->
      <div v-if="result.sections && result.sections.length" class="result-block">
        <div class="block-label">正文章节 ({{ result.sections.length }})</div>
        <div v-for="(sec, i) in result.sections" :key="i" class="section-item">
          <div class="section-heading">{{ sec.heading || `第 ${i + 1} 节` }}</div>
          <div class="section-body">{{ sec.body || sec.content || sec }}</div>
        </div>
      </div>
      <!-- CTA -->
      <div v-if="result.cta" class="result-block">
        <div class="block-label">行动号召 (CTA)</div>
        <div class="block-text">{{ result.cta }}</div>
      </div>
      <!-- 关键词 -->
      <div v-if="result.keywords && result.keywords.length" class="result-block">
        <div class="block-label">关键词</div>
        <div class="keyword-row">
          <span v-for="kw in result.keywords" :key="kw" class="keyword-tag">{{ kw }}</span>
        </div>
      </div>
      <!-- Markdown 预览 -->
      <div v-if="result.markdown" class="result-block">
        <details>
          <summary class="block-label" style="cursor:pointer">Markdown 源码</summary>
          <pre class="result-pre">{{ result.markdown }}</pre>
        </details>
      </div>
      <!-- 完整 JSON -->
      <details class="result-block">
        <summary class="detail-summary">查看完整 JSON</summary>
        <pre class="result-pre">{{ JSON.stringify(result, null, 2) }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import labels from '../../i18n/labels.js'

const L = labels
const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const input = reactive({
  input_mode: 'inline', source_text: '', key_points: '', tone: 'professional',
  length_target: 1500, title_count: 5, use_llm: true, llm_provider: '', llm_model: '',
})
const result = ref(null)
const loading = ref(false)
const canGenerate = computed(() => appStore.projectDir && input.source_text.trim().length > 0)

async function generate() {
  if (!canGenerate.value || loading.value) return
  loading.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/article_expand/generate', {
      input_mode: input.input_mode, source_text: input.source_text, key_points: input.key_points,
      tone: input.tone, length_target: input.length_target, title_count: input.title_count,
      use_llm: input.use_llm, llm_provider: input.llm_provider, llm_model: input.llm_model,
    })
    if (data.error) { capStore.setMessage(`公众号扩写失败：${data.error}`, 'error'); return }
    result.value = data.result || null
    capStore.setMessage(`公众号扩写完成：生成标题 ${result.value?.title_candidates?.length || 0} 条`, 'success')
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
.form-row label { width: 80px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.title-candidate { font-size: 13px; padding: 4px 0; }
.result-block { margin-bottom: 14px; }
.block-label { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }
.block-text { font-size: 13px; line-height: 1.6; }
.section-item { margin-bottom: 10px; padding: 8px 12px; background: var(--surface2); border-radius: 6px; }
.section-heading { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.section-body { font-size: 12px; line-height: 1.5; color: var(--text); }
.keyword-row { display: flex; flex-wrap: wrap; gap: 6px; }
.keyword-tag { font-size: 11px; padding: 2px 8px; background: rgba(90,141,238,0.12); color: var(--accent); border-radius: 10px; }
.detail-summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
.form-hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
</style>
