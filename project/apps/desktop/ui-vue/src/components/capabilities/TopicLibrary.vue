<template>
  <div>
    <h3>选题库</h3>
    <div class="cap-section">
      <div class="form-row">
        <label>搜索</label>
        <input v-model="query" placeholder="关键词" class="form-input" @keyup.enter="load" />
      </div>
      <div class="form-row">
        <label>分类</label>
        <input v-model="category" :placeholder="L.panelHints.topicLibrary.categoryPlaceholder" class="form-input" />
      </div>
      <div class="btn-row">
        <button class="btn btn-sm" @click="load" :disabled="!appStore.projectDir || loadingQuery">{{ loadingQuery ? '查询中…' : '查询' }}</button>
        <button class="btn btn-sm" @click="bootstrap" :disabled="!appStore.projectDir || loadingBootstrap">{{ loadingBootstrap ? '生成中…' : '从素材生成' }}</button>
      </div>
    </div>

    <div v-if="items.length" class="cap-section">
      <div class="cap-subtitle">共 {{ items.length }} 条模板</div>
      <div v-for="item in items" :key="item.slug" class="topic-item" @click="useTemplate(item)">
        <strong>{{ item.title || item.slug }}</strong>
        <span class="text-muted" style="margin-left:8px">{{ item.category || '' }}</span>
        <div v-if="item.tags && item.tags.length" class="tag-row">
          <span v-for="t in item.tags" :key="t" class="badge badge-info">{{ t }}</span>
        </div>
      </div>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">新建 / 编辑模板</div>
      <div class="form-row"><label>标题</label><input v-model="form.title" class="form-input" /></div>
      <div class="form-row"><label>标识符</label><input v-model="form.slug" class="form-input" placeholder="唯一标识" /></div>
      <div class="form-row"><label>分类</label><input v-model="form.category" class="form-input" :placeholder="L.panelHints.topicLibrary.categoryPlaceholder" /></div>
      <div class="form-row"><label>受众</label><input v-model="form.audience" class="form-input" placeholder="短视频" /></div>
      <div class="form-row"><label>开头风格</label><input v-model="form.hook_style" class="form-input" placeholder="故事型" /></div>
      <div class="form-row"><label>标签</label><input v-model="form.tags" class="form-input" placeholder="逗号分隔" /></div>
      <div class="form-row"><label>大纲模板</label><textarea v-model="form.outline_template" class="form-input" rows="3"></textarea></div>
      <button class="btn btn-primary btn-sm" @click="save" :disabled="!appStore.projectDir || !form.title.trim() || loadingSave">{{ loadingSave ? '保存中…' : '保存模板' }}</button>
      <div v-if="!form.title.trim() && appStore.projectDir" class="form-hint">请先填写选题标题</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, inject } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import labels from '../../i18n/labels.js'

const L = labels
const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

// Phase 2: IdeateView 联动 — 广播选中的 slug 给 TopicCopy
const ideateSelectedSlug = inject('ideateSelectedSlug', null)

const query = ref('')
const category = ref('')
const items = ref([])
const loadingQuery = ref(false)
const loadingBootstrap = ref(false)
const loadingSave = ref(false)
const form = reactive({
  title: '', slug: '', category: '', audience: '',
  hook_style: '', outline_template: '', tags: '',
})

async function load() {
  if (!appStore.projectDir || loadingQuery.value) return
  loadingQuery.value = true
  try {
    const q = encodeURIComponent(query.value || '')
    const cat = encodeURIComponent(category.value || '')
    const data = await apiStore.api('GET', `/api/capabilities/topic_library?q=${q}&category=${cat}&limit=120`)
    if (data.error) { capStore.setMessage(`选题库读取失败：${data.error}`, 'error'); return }
    items.value = Array.isArray(data.topics) ? data.topics : []
  } finally {
    loadingQuery.value = false
  }
}

async function bootstrap() {
  if (!appStore.projectDir || loadingBootstrap.value) return
  loadingBootstrap.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/topic_library/bootstrap', {})
    if (data.error) { capStore.setMessage(`选题库初始化失败：${data.error}`, 'error'); return }
    capStore.setMessage(`选题库已从素材生成模板 ${data.created || 0} 条`, 'success')
    await load()
  } finally {
    loadingBootstrap.value = false
  }
}

function useTemplate(item) {
  if (!item) return
  form.slug = item.slug || ''
  form.title = item.title || ''
  form.category = item.category || ''
  form.audience = item.audience || ''
  form.hook_style = item.hook_style || ''
  form.outline_template = item.outline_template || ''
  form.tags = Array.isArray(item.tags) ? item.tags.join(',') : ''
  // Phase 2: 广播 slug 给 TopicCopy（仅在 IdeateView 内生效）
  if (ideateSelectedSlug) ideateSelectedSlug.value = item.slug || ''
}

async function save() {
  if (!appStore.projectDir || loadingSave.value) return
  if (!form.title.trim()) { capStore.setMessage('请先填写选题标题', 'warning'); return }
  loadingSave.value = true
  try {
    const tags = form.tags.replace(/，/g, ',').split(',').map(x => x.trim()).filter(Boolean)
    const payload = {
      slug: form.slug, title: form.title, category: form.category,
      audience: form.audience, hook_style: form.hook_style,
      outline_template: form.outline_template, tags, enabled: true,
    }
    const data = await apiStore.api('POST', '/api/capabilities/topic_library', payload)
    if (data.error) { capStore.setMessage(`保存失败：${data.error}`, 'error'); return }
    capStore.setMessage(`选题模板已保存：${data.slug || form.title}`, 'success')
    await load()
  } finally {
    loadingSave.value = false
  }
}

onMounted(() => { if (appStore.projectDir) load() })
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 80px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 8px; margin-top: 8px; }
.topic-item { padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 6px; cursor: pointer; transition: background 0.15s; }
.topic-item:hover { background: var(--surface2); }
.tag-row { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
.form-hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
</style>
