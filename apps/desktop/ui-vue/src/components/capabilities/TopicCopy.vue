<template>
  <div>
    <h3>选题文案</h3>
    <div class="cap-section">
      <div class="form-row"><label>选题 Slug</label><input v-model="form.slug" class="form-input" placeholder="从选题库选择或手动输入" /></div>
      <div class="form-row"><label>目标时长(秒)</label><input v-model.number="form.target_duration_s" type="number" class="form-input" /></div>
      <button class="btn btn-primary btn-sm" @click="generate" :disabled="!appStore.projectDir">生成文案草案</button>
    </div>
    <div v-if="draft" class="cap-section">
      <div class="cap-subtitle">生成结果</div>
      <pre class="result-pre">{{ JSON.stringify(draft, null, 2) }}</pre>
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

const form = reactive({ slug: '', target_duration_s: 60 })
const draft = ref(null)

async function generate() {
  if (!appStore.projectDir) return
  const data = await apiStore.api('POST', '/api/capabilities/topic_copy/draft', {
    slug: form.slug, target_duration_s: form.target_duration_s || 60,
  })
  if (data.error) { capStore.setMessage(`文案草案生成失败：${data.error}`, 'error'); return }
  draft.value = data.draft || null
  capStore.setMessage('已生成选题+文案草案', 'success')
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 100px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
</style>
