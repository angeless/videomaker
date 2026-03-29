<template>
  <div class="ingest-progress" style="margin-top: 12px">
    <!-- 进度条 -->
    <div v-if="lib.ingestLoading" class="progress-bar" style="margin-bottom: 8px">
      <div
        class="progress-bar-fill"
        :style="{ width: Math.min(lib.ingestProgress, 100) + '%' }"
      ></div>
    </div>

    <!-- 结构化进度信息 -->
    <div v-if="lib.ingestLoading && meta.current_file" class="ingest-file-info">
      <span class="current-file">正在处理：{{ meta.current_file }}</span>
      <span class="file-count">（{{ meta.processed }}/{{ meta.total }}，{{ Math.round(meta.percent) }}%）</span>
    </div>

    <!-- 状态文字 -->
    <div class="ingest-status">
      <span v-if="lib.ingestLoading && !meta.current_file" class="ai-spinner">
        {{ labels.library.analyzing }}（{{ Math.round(lib.ingestProgress) }}%）
      </span>
      <span v-else-if="!lib.ingestLoading && lib.ingestMessage" :class="lib.ingestMessage.includes('失败') ? 'text-danger' : 'text-success'">
        {{ lib.ingestMessage }}
      </span>
    </div>

    <!-- 日志 -->
    <LogViewer
      v-if="lib.ingestLog.length > 0"
      :lines="formattedLog"
      style="margin-top: 8px"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useLibraryStore } from '../../stores/library.js'
import labels from '../../i18n/labels.js'
import LogViewer from '../common/LogViewer.vue'

const lib = useLibraryStore()

const meta = computed(() => lib.ingestMeta)

const formattedLog = computed(() => {
  return lib.ingestLog.map(entry => {
    if (typeof entry === 'string') return entry
    if (entry.message) return `${entry.timestamp || ''} ${entry.message}`
    return JSON.stringify(entry)
  })
})
</script>

<style scoped>
.ingest-status {
  font-size: 13px;
}
.ingest-file-info {
  font-size: 13px;
  margin-bottom: 4px;
}
.current-file {
  font-weight: 500;
}
.file-count {
  color: var(--muted);
}
</style>
