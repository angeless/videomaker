<template>
  <div>
    <h3>公众号扩写</h3>
    <div class="cap-section">
      <div class="form-row"><label>源文本</label><textarea v-model="input.source_text" class="form-input" rows="4" placeholder="粘贴原始文案"></textarea></div>
      <div class="form-row"><label>要点</label><input v-model="input.key_points" class="form-input" placeholder="逗号分隔关键点" /></div>
      <div class="form-row"><label>语气</label>
        <select v-model="input.tone" class="form-input"><option value="professional">专业</option><option value="casual">轻松</option><option value="humorous">幽默</option></select>
      </div>
      <div class="form-row"><label>目标字数</label><input v-model.number="input.length_target" type="number" class="form-input" /></div>
      <div class="form-row"><label>标题数量</label><input v-model.number="input.title_count" type="number" class="form-input" /></div>
      <div class="form-row"><label>使用 LLM</label><input type="checkbox" v-model="input.use_llm" /></div>
      <button class="btn btn-primary btn-sm" @click="generate" :disabled="!canGenerate || loading">{{ loading ? '生成中…' : '生成扩写' }}</button>
      <div v-if="!input.source_text.trim() && appStore.projectDir" class="form-hint">请先粘贴源文本</div>
    </div>
    <div v-if="result" class="cap-section">
      <div class="cap-subtitle">扩写结果</div>
      <div v-if="result.title_candidates && result.title_candidates.length" style="margin-bottom:12px">
        <div class="cap-subtitle">候选标题</div>
        <div v-for="(t, i) in result.title_candidates" :key="i" class="title-candidate">{{ i + 1 }}. {{ t }}</div>
      </div>
      <pre class="result-pre">{{ JSON.stringify(result, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const input = reactive({
  input_mode: 'inline', source_text: '', key_points: '', tone: 'professional',
  length_target: 1200, title_count: 5, use_llm: true, llm_provider: '', llm_model: '',
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
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
.form-hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
</style>
