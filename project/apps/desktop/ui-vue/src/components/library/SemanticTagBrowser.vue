<template>
  <div v-if="categories.length > 0" class="semantic-browser">
    <div class="browser-header" @click="expanded = !expanded">
      <span class="browser-title">语义标签 ({{ totalTags }})</span>
      <span class="browser-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-if="expanded" class="browser-body">
      <div v-for="cat in categories" :key="cat.key" class="tag-cat">
        <div class="tag-cat-header">
          <span class="tag-cat-name">{{ cat.label }}</span>
          <span class="tag-cat-count">{{ cat.tags.length }}</span>
        </div>
        <div class="tag-cat-tags">
          <span
            v-for="tag in cat.tags"
            :key="tag"
            class="tag clickable"
            @click="$emit('search', tag)"
          >{{ tag }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { translateTag } from '../../composables/useSemanticTranslation.js'

const props = defineProps({
  semantic: { type: Object, default: () => ({}) },
})

defineEmits(['search'])

const expanded = ref(false)

const categoryLabels = {
  objects: '物体', actions: '动作', scene: '场景', mood: '氛围',
  concepts: '概念', style: '风格', use_cases: '用途',
  materials_textures: '材质纹理', architecture_style: '建筑风格',
  food_cuisine: '美食类型', animal_species: '动物种类',
  vehicle_transport: '交通工具', clothing_fashion: '服饰时尚',
  body_language: '身体语言', spatial_relations: '空间关系',
  cultural_elements: '文化元素', brand_product: '品牌产品',
  audio_mood: '音频氛围', color_palette: '色彩搭配',
  composition: '构图方式', nature_landscape: '自然景观',
  weather_atmosphere: '天气氛围', social_context: '社交语境',
  industry_domain: '行业领域', narrative_technique: '叙事手法',
}

const categories = computed(() => {
  const st = props.semantic?.structured_tags
  if (!st || typeof st !== 'object') return []

  const cats = []
  for (const [key, data] of Object.entries(st)) {
    // data can be {zh:[], en:[], confidence:0} or just an array
    let tags = []
    if (Array.isArray(data)) {
      tags = data
    } else if (data && typeof data === 'object') {
      // Prefer zh, fallback en
      const zh = Array.isArray(data.zh) ? data.zh : []
      const en = Array.isArray(data.en) ? data.en : []
      tags = zh.length > 0 ? zh : en.map(t => translateTag(t))
    }
    if (tags.length === 0) continue
    cats.push({
      key,
      label: categoryLabels[key] || key,
      tags: tags.slice(0, 20),
    })
  }
  return cats
})

const totalTags = computed(() => {
  return categories.value.reduce((sum, c) => sum + c.tags.length, 0)
})
</script>

<style scoped>
.semantic-browser {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-top: 8px;
}

.browser-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--surface2);
  cursor: pointer;
  user-select: none;
}

.browser-title {
  font-size: 12px;
  font-weight: 600;
}

.browser-toggle {
  font-size: 11px;
  color: var(--muted);
}

.browser-body {
  padding: 8px 12px;
}

.tag-cat {
  margin-bottom: 8px;
}

.tag-cat:last-child {
  margin-bottom: 0;
}

.tag-cat-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.tag-cat-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}

.tag-cat-count {
  font-size: 10px;
  color: var(--muted);
  opacity: 0.6;
}

.tag-cat-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.clickable {
  cursor: pointer;
  transition: background 0.15s;
}

.clickable:hover {
  background: rgba(90, 141, 238, 0.2);
}
</style>
