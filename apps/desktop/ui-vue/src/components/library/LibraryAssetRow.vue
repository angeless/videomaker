<template>
  <div class="asset-row">
    <!-- 缩略图 -->
    <div class="row-thumb">
      <img v-if="asset.thumbnail_url" :src="asset.thumbnail_url" :alt="asset.filename" loading="lazy" />
      <span v-else class="row-thumb-placeholder">{{ asset.asset_kind === 'video' ? '🎬' : '🖼️' }}</span>
    </div>

    <!-- 文件名 -->
    <div class="row-name" :title="asset.filename">{{ asset.filename || '未知文件' }}</div>

    <!-- 类型 -->
    <span class="badge badge-info row-kind">{{ asset.asset_kind === 'video' ? '视频' : '图片' }}</span>

    <!-- 时长 -->
    <span class="row-meta">{{ asset.duration ? formatDuration(asset.duration) : '—' }}</span>

    <!-- 分辨率 -->
    <span class="row-meta">{{ asset.resolution || '—' }}</span>

    <!-- 标签(前3) -->
    <div class="row-tags">
      <span v-for="tag in topTags" :key="tag" class="tag">{{ tag }}</span>
    </div>

    <!-- 质量分 -->
    <span v-if="asset.quality_score" class="quality-badge" title="画面质量评分（0-1），综合考虑清晰度、构图和光线">{{ qualityLabel(asset.quality_score) }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { translateAndDedupe } from '../../composables/useSemanticTranslation.js'

const props = defineProps({
  asset: { type: Object, required: true },
})

function qualityLabel(score) {
  const n = Number(score)
  if (n >= 0.9) return '优秀'
  if (n >= 0.7) return '良好'
  if (n >= 0.5) return '一般'
  return '较差'
}

const topTags = computed(() => {
  const raw = props.asset.semantic_keywords || []
  return translateAndDedupe(raw).slice(0, 3)
})

function formatDuration(seconds) {
  const s = Number(seconds) || 0
  if (s < 60) return `${Math.round(s)}s`
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.asset-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}

.asset-row:hover {
  background: var(--surface2);
}

.row-thumb {
  width: 48px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 4px;
  overflow: hidden;
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.row-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.row-thumb-placeholder {
  font-size: 18px;
  opacity: 0.3;
}

.row-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.row-kind {
  flex-shrink: 0;
}

.row-meta {
  font-size: 11px;
  color: var(--muted);
  width: 60px;
  text-align: center;
  flex-shrink: 0;
}

.row-tags {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  max-width: 200px;
  overflow: hidden;
}

.quality-badge {
  background: rgba(90, 141, 238, 0.15);
  color: var(--accent);
  font-size: 10px;
  padding: 0 4px;
  border-radius: 3px;
  flex-shrink: 0;
}
</style>
