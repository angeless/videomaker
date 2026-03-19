<template>
  <div>
    <h3>发布文案</h3>
    <div class="cap-section">
      <div class="form-row"><label>脚本文案</label><textarea v-model="input.script_text" class="form-input" rows="3" placeholder="粘贴脚本文案"></textarea></div>
      <div class="form-row"><label>旁白文案</label><textarea v-model="input.voiceover_text" class="form-input" rows="2" placeholder="粘贴旁白"></textarea></div>
      <div class="form-row"><label>目标平台</label><input v-model="input.platforms" class="form-input" placeholder="YouTube, 抖音, 小红书 (逗号分隔)" /></div>
      <div class="form-row"><label>内容类型</label>
        <select v-model="input.platform_content_type" class="form-input"><option value="video_post">视频</option><option value="article">文章</option></select>
      </div>
      <div class="form-row"><label>启用 AI 辅助</label><input type="checkbox" v-model="input.use_llm" /></div>
      <button class="btn btn-primary btn-sm" @click="generate" :disabled="!canGenerate || loading">{{ loading ? '生成中…' : '生成发布文案' }}</button>
      <div v-if="!input.script_text.trim() && !input.voiceover_text.trim() && appStore.projectDir" class="form-hint">请先填写脚本文案或旁白文案</div>
    </div>
    <div v-if="result" class="cap-section">
      <div class="cap-subtitle">生成结果 (覆盖 {{ result.platform_results?.length || 0 }} 个平台)</div>
      <div v-for="pr in (result.platform_results || [])" :key="pr.platform" class="platform-card">
        <div class="platform-name">{{ pr.platform }}</div>
        <div v-if="pr.title" class="platform-field"><span class="field-label">标题</span>{{ pr.title }}</div>
        <div v-if="pr.description" class="platform-field"><span class="field-label">描述</span>{{ pr.description }}</div>
        <div v-if="pr.keywords && pr.keywords.length" class="platform-field">
          <span class="field-label">关键词</span>
          <span v-for="kw in pr.keywords" :key="kw" class="kw-tag">{{ kw }}</span>
        </div>
        <div v-if="pr.hashtags && pr.hashtags.length" class="platform-field">
          <span class="field-label">标签</span>
          <span class="field-text">{{ pr.hashtags.join(' ') }}</span>
        </div>
      </div>
      <details v-if="result.warnings && result.warnings.length" style="margin-top:8px">
        <summary class="detail-summary">警告 ({{ result.warnings.length }})</summary>
        <div v-for="(w, i) in result.warnings" :key="i" class="warn-line">{{ w }}</div>
      </details>
      <details style="margin-top:8px">
        <summary class="detail-summary">查看完整 JSON</summary>
        <pre class="result-pre">{{ JSON.stringify(result, null, 2) }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const input = reactive({
  input_mode: 'inline', script_text: '', voiceover_text: '', platforms: '',
  platform_content_type: 'video_post', use_saved_profiles: true,
  profile_overrides_json: '{}', use_llm: true, llm_provider: '', llm_model: '',
})
const result = ref(null)
const loading = ref(false)
const canGenerate = computed(() => appStore.projectDir && (input.script_text.trim().length > 0 || input.voiceover_text.trim().length > 0))

onMounted(async () => {
  if (appStore.projectDir && !input.script_text.trim()) {
    try {
      const data = await apiStore.api('GET', '/api/script')
      if (data && !data.error && Array.isArray(data.clips)) {
        const narrations = data.clips.map(c => c.narration || '').filter(Boolean)
        if (narrations.length) {
          input.script_text = narrations.join('\n')
        }
      }
    } catch { /* silent — script may not exist yet */ }
  }
})

async function generate() {
  if (!canGenerate.value || loading.value) return
  loading.value = true
  try {
    let overrides = {}
    try { overrides = JSON.parse(input.profile_overrides_json) } catch { capStore.setMessage('profile_overrides_json 需为 JSON 对象', 'error'); return }
    const platforms = input.platforms.replace(/\n/g, ',').replace(/，/g, ',').split(',').map(x => x.trim()).filter(Boolean)
    const data = await apiStore.api('POST', '/api/capabilities/publish_prep/generate', {
      input_mode: input.input_mode, script_text: input.script_text, voiceover_text: input.voiceover_text,
      platforms, platform_content_type: input.platform_content_type,
      use_saved_profiles: input.use_saved_profiles, profile_overrides: overrides,
      use_llm: input.use_llm, llm_provider: input.llm_provider, llm_model: input.llm_model,
    })
    if (data.error) { capStore.setMessage(`发布文案生成失败：${data.error}`, 'error'); return }
    result.value = data.result || null
    capStore.setMessage(`发布文案生成完成：覆盖 ${result.value?.platform_results?.length || 0} 个平台`, 'success')
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
.platform-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 10px; }
.platform-name { font-size: 13px; font-weight: 600; color: var(--accent); margin-bottom: 6px; }
.platform-field { font-size: 12px; margin-bottom: 4px; line-height: 1.5; }
.field-label { font-weight: 600; color: var(--muted); margin-right: 6px; }
.field-text { color: var(--text); }
.kw-tag { display: inline-block; font-size: 11px; padding: 1px 6px; background: rgba(90,141,238,0.12); color: var(--accent); border-radius: 10px; margin-right: 4px; }
.detail-summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.warn-line { font-size: 11px; color: var(--warning, #f0ad4e); padding: 2px 0; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
.form-hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
</style>
