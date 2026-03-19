<template>
  <div>
    <h3>选题文案</h3>
    <div class="cap-section">
      <div class="form-row"><label>{{ L.panelHints.topicCopy.slugLabel }}</label><input v-model="form.slug" class="form-input" :placeholder="L.panelHints.topicCopy.slugPlaceholder" /></div>
      <div class="form-row"><label>目标时长(秒)</label><input v-model.number="form.target_duration_s" type="number" class="form-input" :placeholder="L.panelHints.topicCopy.targetDurationPlaceholder" /></div>
      <button class="btn btn-primary btn-sm" @click="generate" :disabled="!canGenerate || loading">{{ loading ? '生成中…' : '生成文案草案' }}</button>
      <div v-if="!form.slug.trim() && appStore.projectDir" class="form-hint">请先输入选题标识符或从上方选题库选择</div>
    </div>
    <div v-if="draft" class="cap-section">
      <div class="cap-subtitle">生成结果</div>
      <div class="draft-card">
        <div v-if="draft.title || draft.topic_name || draft.hook" class="draft-title">{{ draft.title || draft.topic_name || draft.hook || '未命名选题' }}</div>
        <div v-if="draft.hook && (draft.title || draft.topic_name)" class="draft-hook">{{ draft.hook }}</div>
        <div v-if="draft.body || draft.outline" class="draft-body">{{ draft.body || (Array.isArray(draft.outline) ? draft.outline.join('\n') : draft.outline) }}</div>
        <div v-if="draft.cta" class="draft-cta">{{ draft.cta }}</div>
        <div v-if="draft.narration_style || draft.target_duration_s" class="draft-meta">
          <span v-if="draft.narration_style" class="draft-meta-item">叙事风格：{{ draft.narration_style }}</span>
          <span v-if="draft.target_duration_s" class="draft-meta-item">目标时长：{{ draft.target_duration_s }}秒</span>
        </div>
        <div v-if="draft.tags && draft.tags.length" class="draft-tags">
          <span v-for="t in draft.tags" :key="t" class="tag">{{ t }}</span>
        </div>
        <div v-if="draft.matched_signals && draft.matched_signals.filter(x => x !== 'unknown').length" class="draft-signals">
          <span class="draft-meta-label">灵感来源：</span>
          <span v-for="s in draft.matched_signals.filter(x => x !== 'unknown')" :key="s" class="tag">{{ translateTag(s) }}</span>
        </div>
        <details class="draft-raw">
          <summary>查看原始数据</summary>
          <pre class="result-pre">{{ JSON.stringify(draft, null, 2) }}</pre>
        </details>
        <button class="btn btn-sm btn-accent draft-import-btn" @click="importToWorkflow">
          导入到工作流
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, inject, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import { useWorkflowStore } from '../../stores/workflow.js'
import labels from '../../i18n/labels.js'
import { translateTag } from '../../composables/useSemanticTranslation.js'

const L = labels
const router = useRouter()
const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()
const workflow = useWorkflowStore()

const form = reactive({ slug: '', target_duration_s: 60 })
const draft = ref(null)
const loading = ref(false)
const canGenerate = computed(() => appStore.projectDir && form.slug.trim().length > 0)

// Phase 2: IdeateView 联动 — 接收 TopicLibrary 选中的 slug
const ideateSelectedSlug = inject('ideateSelectedSlug', null)
if (ideateSelectedSlug) {
  watch(ideateSelectedSlug, (newSlug) => {
    if (newSlug) form.slug = newSlug
  })
}

function importToWorkflow() {
  if (!draft.value) return
  const d = draft.value
  const topic = {
    slug: form.slug || d.slug || '',
    title: d.title || d.topic_name || d.hook || '未命名选题',
    hook: d.hook || '',
    tags: d.tags || d.matched_signals || [],
  }
  // Push to workflow step 2 topics + select it
  if (!workflow.topics.some(t => t.slug === topic.slug)) {
    workflow.topics.push(topic)
  }
  workflow.selectedTopic = topic
  workflow.topicCustom = ''
  capStore.setMessage('已导入到工作流选题', 'success')
  router.push('/create/workflow/2')
}

async function generate() {
  if (!canGenerate.value || loading.value) return
  loading.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/topic_copy/draft', {
      slug: form.slug, target_duration_s: form.target_duration_s || 60,
    })
    if (data.error) { capStore.setMessage(`文案草案生成失败：${data.error}`, 'error'); return }
    draft.value = data.draft || null
    capStore.setMessage('已生成选题+文案草案', 'success')
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
.form-row label { width: 100px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
.draft-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.draft-title { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
.draft-hook { font-size: 13px; color: var(--accent); margin-bottom: 8px; font-style: italic; }
.draft-body { font-size: 13px; line-height: 1.7; white-space: pre-wrap; margin-bottom: 10px; }
.draft-cta { font-size: 13px; color: var(--accent); font-weight: 500; margin-bottom: 10px; }
.draft-meta { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 10px; }
.draft-meta-item { font-size: 11px; color: var(--muted); }
.draft-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.draft-signals { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 8px; }
.draft-meta-label { font-size: 11px; color: var(--muted); }
.draft-raw { margin-top: 8px; }
.draft-raw summary { font-size: 11px; color: var(--muted); cursor: pointer; }
.form-hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
.draft-import-btn { margin-top: 12px; }
.btn-accent { background: var(--accent); color: #fff; border: none; cursor: pointer; padding: 6px 14px; border-radius: 6px; font-size: 12px; }
.btn-accent:hover { opacity: 0.85; }
</style>
