<template>
  <div class="tag-browser">
    <div class="tag-browser-header" @click="expanded = !expanded">
      <span class="tag-browser-icon">{{ expanded ? '▾' : '▸' }}</span>
      <span class="tag-browser-title">标签浏览</span>
      <span v-if="totalTags > 0" class="tag-browser-count">{{ totalTags }} 个标签</span>
    </div>

    <div v-if="expanded" class="tag-browser-body">
      <div v-if="loading" class="tag-browser-loading">加载中...</div>
      <div v-else-if="categories.length === 0" class="tag-browser-empty">暂无标签数据</div>
      <div v-else>
        <div v-for="cat in categories" :key="cat.category_id" class="tag-cat">
          <div class="tag-cat-header" @click="toggleCat(cat.category_id)">
            <span class="cat-toggle">{{ openCats.has(cat.category_id) ? '▾' : '▸' }}</span>
            <span class="cat-name">{{ cat.category_name }}</span>
            <span class="cat-count">{{ cat.tags.length }}</span>
          </div>
          <div v-if="openCats.has(cat.category_id)" class="tag-cat-tags">
            <span
              v-for="tag in cat.tags"
              :key="tag.tag_id"
              class="browser-tag"
              :title="`${tag.asset_count} 个素材`"
              @click="onClickTag(tag)"
            >
              {{ tag.tag_name }}
              <span v-if="tag.asset_count > 0" class="tag-asset-count">{{ tag.asset_count }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useApiStore } from '../../stores/api.js'

const emit = defineEmits(['search-tag'])

const api = useApiStore()
const expanded = ref(false)
const loading = ref(false)
const categories = ref([])
const openCats = reactive(new Set())

const totalTags = computed(() => {
  return categories.value.reduce((sum, c) => sum + c.tags.length, 0)
})

async function fetchTags() {
  if (categories.value.length > 0) return // already loaded
  loading.value = true
  const data = await api.api('GET', '/api/library/tags')
  loading.value = false
  if (data.error) return
  categories.value = (data.categories || []).filter(c => c.tags && c.tags.length > 0)
}

function toggleCat(catId) {
  if (openCats.has(catId)) {
    openCats.delete(catId)
  } else {
    openCats.add(catId)
  }
}

function onClickTag(tag) {
  emit('search-tag', tag.tag_name)
}

onMounted(() => {
  // Lazy load — only fetch when expanded
})

// Watch expanded to fetch
import { watch } from 'vue'
watch(expanded, (val) => {
  if (val) fetchTags()
})
</script>

<style scoped>
.tag-browser {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
}

.tag-browser-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.tag-browser-header:hover {
  background: var(--surface2);
}

.tag-browser-icon {
  font-size: 11px;
  color: var(--muted);
  width: 14px;
}

.tag-browser-title {
  font-size: 13px;
  font-weight: 600;
}

.tag-browser-count {
  font-size: 11px;
  color: var(--muted);
  margin-left: auto;
}

.tag-browser-body {
  border-top: 1px solid var(--border);
  max-height: 400px;
  overflow-y: auto;
}

.tag-browser-loading,
.tag-browser-empty {
  padding: 16px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.tag-cat {
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.tag-cat:last-child {
  border-bottom: none;
}

.tag-cat-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.1s;
}

.tag-cat-header:hover {
  background: var(--surface2);
}

.cat-toggle {
  font-size: 10px;
  color: var(--muted);
  width: 12px;
}

.cat-name {
  font-size: 12px;
  font-weight: 500;
}

.cat-count {
  font-size: 10px;
  color: var(--muted);
  margin-left: auto;
  background: rgba(255,255,255,0.06);
  padding: 1px 6px;
  border-radius: 8px;
}

.tag-cat-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 4px 14px 10px 30px;
}

.browser-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(90, 141, 238, 0.1);
  color: var(--accent);
  cursor: pointer;
  transition: background 0.15s;
  user-select: none;
}

.browser-tag:hover {
  background: rgba(90, 141, 238, 0.25);
}

.tag-asset-count {
  font-size: 9px;
  color: var(--muted);
  background: rgba(255,255,255,0.08);
  padding: 0 4px;
  border-radius: 6px;
}
</style>
