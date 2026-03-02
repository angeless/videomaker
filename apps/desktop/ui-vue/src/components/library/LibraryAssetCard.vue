<template>
  <div class="asset-card card">
    <!-- 缩略图 -->
    <div class="asset-thumb">
      <div v-if="asset.media_type === 'image' && asset.thumbnail_url" class="asset-thumb-img">
        <img :src="asset.thumbnail_url" :alt="asset.filename" />
      </div>
      <div v-else class="asset-thumb-placeholder">
        {{ asset.media_type === 'video' ? '🎬' : '🖼️' }}
      </div>
      <span v-if="asset.duration" class="asset-duration">{{ formatDuration(asset.duration) }}</span>
    </div>

    <!-- 信息 -->
    <div class="asset-info">
      <div class="asset-filename" :title="asset.filename">{{ asset.filename || '未知文件' }}</div>

      <div v-if="asset.resolution" class="asset-meta">
        {{ asset.resolution }}
      </div>

      <div v-if="displayLocation" class="asset-meta">
        📍 {{ displayLocation }}
      </div>

      <!-- 标签 -->
      <div v-if="translatedTags.length > 0" class="tag-group" style="margin-top: 6px">
        <span v-for="tag in visibleTags" :key="tag" class="tag">{{ tag }}</span>
        <span
          v-if="translatedTags.length > maxVisible"
          class="tag"
          style="cursor: pointer; color: var(--accent)"
          @click="showAll = !showAll"
        >
          {{ showAll ? '收起' : `+${translatedTags.length - maxVisible} ${labels.library.moreTags}` }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { translateAndDedupe } from '../../composables/useSemanticTranslation.js'
import labels from '../../i18n/labels.js'

const props = defineProps({
  asset: { type: Object, required: true },
})

const showAll = ref(false)
const maxVisible = 5

const translatedTags = computed(() => {
  const raw = props.asset.tags || props.asset.semantic_tags || []
  return translateAndDedupe(raw)
})

const visibleTags = computed(() => {
  if (showAll.value) return translatedTags.value
  return translatedTags.value.slice(0, maxVisible)
})

const displayLocation = computed(() => {
  const loc = props.asset.location || props.asset.gps_location
  if (!loc) return ''
  if (typeof loc === 'string') return loc
  if (loc.name) return loc.name
  if (loc.latitude && loc.longitude) return `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`
  return ''
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
.asset-card {
  padding: 0;
  overflow: hidden;
}

.asset-thumb {
  position: relative;
  height: 120px;
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.asset-thumb-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.asset-thumb-placeholder {
  font-size: 36px;
  opacity: 0.3;
}

.asset-duration {
  position: absolute;
  bottom: 4px;
  right: 6px;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
}

.asset-info {
  padding: 10px 12px;
}

.asset-filename {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.asset-meta {
  font-size: 11px;
  color: var(--muted);
}
</style>
