<template>
  <div ref="panelEl" class="card" style="margin-bottom: 16px">
    <div class="card-header" @click="expanded = !expanded" style="cursor: pointer">
      📥 {{ labels.library.ingest }}
      <span style="margin-left: 4px">{{ expanded ? '▾' : '▸' }}</span>
      <div v-if="expanded" style="margin-left: auto; display: flex; gap: 4px" @click.stop>
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="btn btn-sm"
          :class="activeTab === tab.key ? 'btn-primary' : 'btn-ghost'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <template v-if="expanded">
      <!-- 本地视频 -->
      <div v-if="activeTab === 'local'">
        <div class="form-group">
          <label class="form-label">选择视频文件夹</label>
          <div class="form-row">
            <input v-model="lib.ingestLocalPath" class="form-input" readonly placeholder="点击选择…" />
            <button class="btn btn-ghost btn-sm" @click="pickLocalPath">选择文件夹</button>
          </div>
        </div>
        <div class="form-row" style="gap: 8px">
          <button class="btn btn-ghost btn-sm" :disabled="!lib.ingestLocalPath || lib.ingestLocalPreviewLoading" @click="lib.previewLocalIngest()">
            {{ lib.ingestLocalPreviewLoading ? '扫描中…' : '预览扫描' }}
          </button>
          <button class="btn btn-primary btn-sm" :disabled="!lib.ingestLocalPath || lib.ingestLoading" @click="lib.startLocalIngest()">
            {{ lib.ingestLoading ? '入库中…' : '开始入库' }}
          </button>
        </div>
        <div v-if="lib.ingestLocalPreview" class="form-hint" style="margin-top: 8px">
          发现 {{ lib.ingestLocalPreview.sample_videos?.length || 0 }} 个视频文件
        </div>
        <p v-if="lib.ingestLocalPreviewError" class="text-danger" style="font-size: 12px; margin-top: 4px">
          {{ lib.ingestLocalPreviewError }}
        </p>
      </div>

      <!-- 本地图片 -->
      <div v-if="activeTab === 'image'">
        <div class="form-group">
          <label class="form-label">选择图片文件夹</label>
          <div class="form-row">
            <input v-model="lib.ingestImagePath" class="form-input" readonly placeholder="点击选择…" />
            <button class="btn btn-ghost btn-sm" @click="pickImagePath">选择文件夹</button>
          </div>
        </div>
        <div class="form-row" style="gap: 8px">
          <button class="btn btn-ghost btn-sm" :disabled="!lib.ingestImagePath || lib.ingestImagePreviewLoading" @click="lib.previewImageIngest()">
            {{ lib.ingestImagePreviewLoading ? '扫描中…' : '预览扫描' }}
          </button>
          <button class="btn btn-primary btn-sm" :disabled="!lib.ingestImagePath || lib.ingestLoading" @click="lib.startImageIngest()">
            {{ lib.ingestLoading ? '入库中…' : '开始入库' }}
          </button>
        </div>
        <div v-if="lib.ingestImagePreview" class="form-hint" style="margin-top: 8px">
          发现 {{ lib.ingestImagePreview.sample_images?.length || 0 }} 张图片
        </div>
      </div>

      <!-- 入库进度 -->
      <IngestProgress v-if="lib.ingestLoading || lib.ingestMessage" />
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useLibraryStore } from '../../stores/library.js'
import { useApiStore } from '../../stores/api.js'
import labels from '../../i18n/labels.js'
import IngestProgress from './IngestProgress.vue'

const lib = useLibraryStore()
const apiStore = useApiStore()

const expanded = ref(true)
const panelEl = ref(null)

const activeTab = ref('local')
const tabs = [
  { key: 'local', label: labels.library.ingestLocal },
  { key: 'image', label: labels.library.ingestImage },
  // cloud tab hidden — not yet implemented (W-004)
]

async function pickLocalPath() {
  try {
    const result = await apiStore.api('POST', '/api/dialog/folder')
    if (result.path) lib.ingestLocalPath = result.path
  } catch (e) {
    lib.ingestMessage = e.message || '文件夹选择失败'
  }
}

async function pickImagePath() {
  try {
    const result = await apiStore.api('POST', '/api/dialog/folder')
    if (result.path) lib.ingestImagePath = result.path
  } catch (e) {
    lib.ingestMessage = e.message || '文件夹选择失败'
  }
}

// Expose methods for parent to programmatically expand and scroll
defineExpose({
  expand() {
    expanded.value = true
  },
  scrollIntoView(opts) {
    if (panelEl.value) {
      panelEl.value.scrollIntoView(opts || { behavior: 'smooth' })
    }
  },
})
</script>
