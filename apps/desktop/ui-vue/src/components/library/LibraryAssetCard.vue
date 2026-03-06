<template>
  <div class="asset-card card">
    <!-- 缩略图 -->
    <div class="asset-thumb">
      <div v-if="asset.thumbnail_url" class="asset-thumb-img">
        <img :src="asset.thumbnail_url" :alt="asset.filename" loading="lazy" />
      </div>
      <div v-else class="asset-thumb-placeholder">
        {{ asset.asset_kind === 'video' ? '🎬' : '🖼️' }}
      </div>
      <span v-if="asset.duration" class="asset-duration">{{ formatDuration(asset.duration) }}</span>
      <span v-if="asset.asset_kind" class="asset-kind-badge">{{ asset.asset_kind === 'video' ? '视频' : '图片' }}</span>
    </div>

    <!-- 信息 -->
    <div class="asset-info">
      <div class="asset-filename" :title="asset.filename">{{ asset.filename || '未知文件' }}</div>

      <div v-if="asset.resolution" class="asset-meta">
        {{ asset.resolution }}
        <span v-if="asset.quality_score" class="quality-badge">Q{{ asset.quality_score }}</span>
      </div>

      <div v-if="displayLocation" class="asset-meta">
        📍 {{ displayLocation }}
      </div>

      <!-- 语义标签 — 按类展示 -->
      <div v-if="categorizedTags.length > 0" class="tag-section">
        <div v-for="cat in visibleCategories" :key="cat.category" class="tag-category">
          <span class="tag-category-label">{{ cat.label }}</span>
          <span v-for="tag in cat.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
        <span
          v-if="categorizedTags.length > 2"
          class="tag show-more"
          @click="showAll = !showAll"
        >
          {{ showAll ? '收起' : `+${categorizedTags.length - 2} ${labels.library.moreTags}` }}
        </span>
      </div>
      <!-- fallback: flat tags -->
      <div v-else-if="translatedTags.length > 0" class="tag-group" style="margin-top: 6px">
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
import { translateTag, translateAndDedupe } from '../../composables/useSemanticTranslation.js'
import labels from '../../i18n/labels.js'

const props = defineProps({
  asset: { type: Object, required: true },
})

const showAll = ref(false)
const maxVisible = 5

// Category labels (zh)
const categoryLabels = {
  objects: '物体',
  actions: '动作',
  scene: '场景',
  mood: '氛围',
  concepts: '概念',
  style: '风格',
  use_cases: '用途',
  materials_textures: '材质',
  architecture_style: '建筑',
  food_cuisine: '美食',
  animal_species: '动物',
  vehicle_transport: '交通',
  clothing_fashion: '服饰',
  body_language: '肢体',
  spatial_relations: '空间',
  cultural_elements: '文化',
  brand_product: '品牌',
  audio_mood: '音频',
  color_palette: '色彩',
  composition: '构图',
  nature_landscape: '自然',
  weather_atmosphere: '天气',
  social_context: '社交',
  industry_domain: '行业',
  narrative_technique: '叙事',
}

// Extract categorized tags from semantic.structured_tags
const categorizedTags = computed(() => {
  const semantic = props.asset.semantic
  if (!semantic || typeof semantic !== 'object') return []
  const st = semantic.structured_tags
  if (!st || typeof st !== 'object') return []

  const cats = []
  for (const [category, tags] of Object.entries(st)) {
    if (!Array.isArray(tags) || tags.length === 0) continue
    cats.push({
      category,
      label: categoryLabels[category] || category,
      tags: tags.map(t => translateTag(t)).slice(0, 6),
    })
  }
  return cats
})

const visibleCategories = computed(() => {
  if (showAll.value) return categorizedTags.value
  return categorizedTags.value.slice(0, 2)
})

// Flat tags fallback
const translatedTags = computed(() => {
  const raw = props.asset.semantic_keywords || []
  return translateAndDedupe(raw)
})

const visibleTags = computed(() => {
  if (showAll.value) return translatedTags.value
  return translatedTags.value.slice(0, maxVisible)
})

const displayLocation = computed(() => {
  // Direct lat/lng from backend
  const lat = props.asset.gps_latitude
  const lng = props.asset.gps_longitude
  if (lat && lng) return `${Number(lat).toFixed(4)}, ${Number(lng).toFixed(4)}`
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

.asset-thumb-img {
  width: 100%;
  height: 100%;
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

.asset-kind-badge {
  position: absolute;
  top: 4px;
  left: 6px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
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
  display: flex;
  align-items: center;
  gap: 6px;
}

.quality-badge {
  background: rgba(90, 141, 238, 0.15);
  color: var(--accent);
  font-size: 10px;
  padding: 0 4px;
  border-radius: 3px;
}

.tag-section {
  margin-top: 6px;
}

.tag-category {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
  margin-bottom: 3px;
}

.tag-category-label {
  font-size: 10px;
  color: var(--muted);
  font-weight: 600;
  margin-right: 2px;
}

.show-more {
  cursor: pointer;
  color: var(--accent);
}
</style>
