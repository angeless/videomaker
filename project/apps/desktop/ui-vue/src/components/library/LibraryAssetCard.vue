<template>
  <div class="asset-card card" @click="$emit('select', asset)" style="cursor: pointer">
    <!-- 缩略图 -->
    <div class="asset-thumb">
      <div v-if="asset.thumbnail_url" class="asset-thumb-img">
        <img :src="asset.thumbnail_url" :alt="asset.filename" loading="lazy" />
      </div>
      <div v-else class="asset-thumb-placeholder">
        <span class="placeholder-icon">{{ asset.asset_kind === 'video' ? '🎬' : '🖼️' }}</span>
        <span class="placeholder-ext">{{ fileExt }}</span>
      </div>
      <span v-if="asset.duration" class="asset-duration">{{ formatDuration(asset.duration) }}</span>
      <span v-if="asset.asset_kind" class="asset-kind-badge">{{ asset.asset_kind === 'video' ? '视频' : '图片' }}</span>
    </div>

    <!-- 信息 -->
    <div class="asset-info">
      <div class="asset-filename" :title="asset.filename">{{ asset.filename || '未知文件' }}</div>

      <div v-if="asset.resolution" class="asset-meta">
        {{ asset.resolution }}
        <span v-if="asset.quality_score" class="quality-badge" title="画面质量评分（0-1），综合考虑清晰度、构图和光线">{{ qualityLabel(asset.quality_score) }}</span>
      </div>

      <div v-if="displayLocation" class="asset-meta">
        📍 {{ displayLocation }}
      </div>

      <!-- P4-2: search match info (when search results) -->
      <div v-if="matchedTags.length > 0" class="match-section">
        <div class="match-tags">
          <span
            v-for="mt in matchedTags"
            :key="mt"
            class="match-tag"
            @click.stop="$emit('show-evidence', { assetId: asset.uid, filename: asset.filename })"
            title="点击查看解释"
          >{{ mt }}</span>
        </div>
        <div v-if="matchSources.length > 0" class="match-sources">
          <span v-for="src in matchSources" :key="src" class="match-source">{{ sourceLabel(src) }}</span>
        </div>
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

defineEmits(['show-evidence', 'select'])

function qualityLabel(score) {
  const n = Number(score)
  if (n >= 0.9) return '优秀'
  if (n >= 0.7) return '良好'
  if (n >= 0.5) return '一般'
  return '较差'
}

const showAll = ref(false)
const maxVisible = 5

// B-03: 无缩略图时显示文件扩展名
const fileExt = computed(() => {
  const fn = props.asset.filename || ''
  const dot = fn.lastIndexOf('.')
  return dot > 0 ? fn.slice(dot).toUpperCase() : ''
})

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

const maxCategories = 10
const visibleCategories = computed(() => {
  if (showAll.value) return categorizedTags.value.slice(0, maxCategories)
  return categorizedTags.value.slice(0, 2)
})

// Flat tags fallback
const translatedTags = computed(() => {
  const raw = props.asset.semantic_keywords || []
  return translateAndDedupe(raw)
})

const maxExpanded = 30
const visibleTags = computed(() => {
  if (showAll.value) return translatedTags.value.slice(0, maxExpanded)
  return translatedTags.value.slice(0, maxVisible)
})

// Phase 3/4: matched tags from search match_info
const matchedTags = computed(() => {
  const info = props.asset.match_info
  if (!info || typeof info !== 'object') return []
  return info.matched_tags || []
})

const matchSources = computed(() => {
  const info = props.asset.match_info
  if (!info || typeof info !== 'object') return []
  return info.match_sources || []
})

function sourceLabel(src) {
  const map = {
    tag: '标签',
    fts: '关键词',
    embedding: '语义',
  }
  return map[src] || src
}

const displayLocation = computed(() => {
  const lat = props.asset.gps_latitude
  const lng = props.asset.gps_longitude
  if (lat && lng) return `${Number(lat).toFixed(4)}, ${Number(lng).toFixed(4)}`
  return ''
})

function formatDuration(seconds) {
  const s = Number(seconds) || 0
  if (s < 60) return `${Math.round(s)}秒`
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${m}分${sec}秒`
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
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.placeholder-icon { font-size: 36px; }
.placeholder-ext { font-size: 10px; font-weight: 600; opacity: 0.7; }

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

/* P4-2: match section */
.match-section {
  margin-top: 6px;
}

.match-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.match-tag {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 3px;
  background: rgba(76, 175, 80, 0.15);
  color: #4caf50;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.match-tag:hover {
  background: rgba(76, 175, 80, 0.3);
}

.match-sources {
  display: flex;
  gap: 4px;
  margin-top: 3px;
}

.match-source {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted);
}

/* Tags */
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
