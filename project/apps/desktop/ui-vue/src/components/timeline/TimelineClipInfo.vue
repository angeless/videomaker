<template>
  <div v-if="clip" class="tl-clip-info card">
    <div class="tl-info-header">
      <strong>#{{ clip.clip_index }}</strong>
      <span class="tl-info-badge" :class="'tl-badge-' + clip.processing_status">
        {{ statusLabel }}
      </span>
      <button class="btn btn-ghost btn-sm tl-info-close" @click="store.selectClip(null)">✕</button>
    </div>
    <div class="tl-info-grid">
      <div class="tl-info-row">
        <span class="tl-info-key">文件</span>
        <span class="tl-info-val">{{ clip.filename || clip.video_id || '-' }}</span>
      </div>
      <div class="tl-info-row">
        <span class="tl-info-key">时长</span>
        <span class="tl-info-val">{{ formatDuration(clip.duration) }}</span>
      </div>
      <div class="tl-info-row">
        <span class="tl-info-key">源片段</span>
        <span class="tl-info-val">{{ formatDuration(clip.source_start) }} → {{ formatDuration(clip.source_end) }}</span>
      </div>
      <div class="tl-info-row">
        <span class="tl-info-key">时间线</span>
        <span class="tl-info-val">{{ formatDuration(clip.timeline_start) }} → {{ formatDuration(clip.timeline_end) }}</span>
      </div>
      <div v-if="clip.has_face" class="tl-info-row">
        <span class="tl-info-key">人脸</span>
        <span class="tl-info-val" style="color: var(--warn)">需美颜处理</span>
      </div>
      <div v-if="clip.scene_description" class="tl-info-row">
        <span class="tl-info-key">场景</span>
        <span class="tl-info-val">{{ clip.scene_description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useTimelineStore } from '../../stores/timeline.js'
import { useFormatters } from '../../composables/useFormatters.js'

const store = useTimelineStore()
const { formatDuration } = useFormatters()

const clip = computed(() => store.selectedClip)

const statusLabel = computed(() => {
  const s = clip.value?.processing_status
  if (s === 'rendered') return '已渲染'
  if (s === 'matched') return '已匹配'
  return '待匹配'
})
</script>

<style scoped>
.tl-clip-info {
  padding: 10px 14px;
  margin-bottom: 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 6px;
}

.tl-info-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.tl-info-close {
  margin-left: auto;
  font-size: 14px;
  padding: 0 4px;
}

.tl-info-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
}

.tl-badge-rendered { background: rgba(52, 211, 153, 0.15); color: var(--success); }
.tl-badge-matched { background: rgba(90, 141, 238, 0.15); color: var(--accent); }
.tl-badge-pending { background: var(--surface2); color: var(--muted); }

.tl-info-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tl-info-row {
  display: flex;
  gap: 8px;
}

.tl-info-key {
  width: 50px;
  flex-shrink: 0;
  color: var(--muted);
}

.tl-info-val {
  color: var(--text);
  word-break: break-all;
}
</style>
