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
        <input v-model="category" placeholder="如 travel" class="form-input" />
      </div>
      <div class="btn-row">
        <button class="btn btn-sm" @click="load" :disabled="!appStore.projectDir">查询</button>
        <button class="btn btn-sm" @click="bootstrap" :disabled="!appStore.projectDir">从素材生成</button>
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
      <div class="form-row"><label>Slug</label><input v-model="form.slug" class="form-input" /></div>
      <div class="form-row"><label>分类</label><input v-model="form.category" class="form-input" placeholder="travel" /></div>
      <div class="form-row"><label>受众</label><input v-model="form.audience" class="form-input" placeholder="short_video" /></div>
      <div class="form-row"><label>开头风格</label><input v-model="form.hook_style" class="form-input" placeholder="story" /></div>
      <div class="form-row"><label>标签</label><input v-model="form.tags" class="form-input" placeholder="逗号分隔" /></div>
      <div class="form-row"><label>大纲模板</label><textarea v-model="form.outline_template" class="form-input" rows="3"></textarea></div>
      <button class="btn btn-primary btn-sm" @click="save" :disabled="!appStore.projectDir">保存模板</button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const query = ref('')
const category = ref('')
const items = ref([])
const form = reactive({
  title: '', slug: '', category: 'travel', audience: 'short_video',
  hook_style: 'story', outline_template: '', tags: '',
})

async function load() {
  if (!appStore.projectDir) return
  const q = encodeURIComponent(query.value || '')
  const cat = encodeURIComponent(category.value || '')
  const data = await apiStore.api('GET', `/api/capabilities/topic_library?q=${q}&category=${cat}&limit=120`)
  if (data.error) { capStore.setMessage(`选题库读取失败：${data.error}`, 'error'); return }
  items.value = Array.isArray(data.topics) ? data.topics : []
}

async function bootstrap() {
  if (!appStore.projectDir) return
  const data = await apiStore.api('POST', '/api/capabilities/topic_library/bootstrap', {})
  if (data.error) { capStore.setMessage(`选题库初始化失败：${data.error}`, 'error'); return }
  capStore.setMessage(`选题库已从素材生成模板 ${data.created || 0} 条`, 'success')
  await load()
}

function useTemplate(item) {
  if (!item) return
  form.slug = item.slug || ''
  form.title = item.title || ''
  form.category = item.category || 'travel'
  form.audience = item.audience || 'short_video'
  form.hook_style = item.hook_style || 'story'
  form.outline_template = item.outline_template || ''
  form.tags = Array.isArray(item.tags) ? item.tags.join(',') : ''
}

async function save() {
  if (!appStore.projectDir) return
  if (!form.title.trim()) { capStore.setMessage('请先填写选题标题', 'warning'); return }
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
</style>
