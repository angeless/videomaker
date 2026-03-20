<template>
  <div class="autocomplete-wrapper" ref="wrapperRef">
    <input
      ref="inputRef"
      v-model="inputValue"
      class="form-input"
      :placeholder="placeholder"
      @input="onInput"
      @keyup.enter="onEnter"
      @keydown.down.prevent="moveDown"
      @keydown.up.prevent="moveUp"
      @keydown.escape="closeSuggestions"
      @focus="onFocus"
    />
    <div v-if="showSuggestions && suggestions.length > 0" class="suggestions-dropdown">
      <div
        v-for="(item, idx) in suggestions"
        :key="`${item.tag_id}-${item.matched_via}`"
        class="suggestion-item"
        :class="{ active: idx === activeIndex }"
        @mousedown.prevent="selectItem(item)"
        @mouseenter="activeIndex = idx"
      >
        <span class="suggestion-name">{{ item.tag_name }}</span>
        <span class="suggestion-via" :class="`via-${item.matched_via}`">
          {{ viaLabel(item.matched_via) }}
        </span>
        <span v-if="item.matched_text && item.matched_via !== 'tag_name'" class="suggestion-alias">
          {{ item.matched_text }}
        </span>
        <span v-if="item.category_name" class="suggestion-category">{{ item.category_name }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useApiStore } from '../../stores/api.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '搜索素材...' },
})

const emit = defineEmits(['update:modelValue', 'search', 'select-tag'])

const api = useApiStore()
const inputRef = ref(null)
const wrapperRef = ref(null)
const inputValue = ref(props.modelValue)
const suggestions = ref([])
const showSuggestions = ref(false)
const activeIndex = ref(-1)
let debounceTimer = null

watch(() => props.modelValue, (val) => {
  inputValue.value = val
})

watch(inputValue, (val) => {
  emit('update:modelValue', val)
})

function viaLabel(via) {
  const map = {
    tag_name: '标签',
    alias: '别名',
    custom_tag: '自定义',
  }
  return map[via] || via
}

async function fetchSuggestions(q) {
  if (!q || q.length < 1) {
    suggestions.value = []
    showSuggestions.value = false
    return
  }
  try {
    const params = new URLSearchParams({ q, limit: '10' })
    const data = await api.api('GET', `/api/library/tags/search?${params}`)
    if (data.error) {
      suggestions.value = []
      return
    }
    suggestions.value = data.results || []
    showSuggestions.value = suggestions.value.length > 0
    activeIndex.value = -1
  } catch {
    suggestions.value = []
  }
}

function onInput() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    fetchSuggestions(inputValue.value.trim())
  }, 200)
}

function onFocus() {
  if (inputValue.value.trim() && suggestions.value.length > 0) {
    showSuggestions.value = true
  }
}

function closeSuggestions() {
  showSuggestions.value = false
  activeIndex.value = -1
}

function selectItem(item) {
  inputValue.value = item.tag_name
  emit('update:modelValue', item.tag_name)
  closeSuggestions()
  emit('select-tag', item)
  emit('search')
}

function onEnter() {
  if (activeIndex.value >= 0 && activeIndex.value < suggestions.value.length) {
    selectItem(suggestions.value[activeIndex.value])
  } else {
    closeSuggestions()
    emit('search')
  }
}

function moveDown() {
  if (!showSuggestions.value) return
  activeIndex.value = Math.min(activeIndex.value + 1, suggestions.value.length - 1)
}

function moveUp() {
  if (!showSuggestions.value) return
  activeIndex.value = Math.max(activeIndex.value - 1, 0)
}

function handleClickOutside(e) {
  if (wrapperRef.value && !wrapperRef.value.contains(e.target)) {
    closeSuggestions()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleClickOutside)
  clearTimeout(debounceTimer)
})
</script>

<style scoped>
.autocomplete-wrapper {
  position: relative;
  flex: 1;
}

.suggestions-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-top: 4px;
  max-height: 320px;
  overflow-y: auto;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.1s;
}

.suggestion-item:hover,
.suggestion-item.active {
  background: var(--surface2);
}

.suggestion-name {
  font-weight: 500;
  flex-shrink: 0;
}

.suggestion-via {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.via-tag_name {
  background: rgba(90, 141, 238, 0.15);
  color: var(--accent);
}

.via-alias {
  background: rgba(255, 183, 77, 0.18);
  color: #ffb74d;
}

.via-custom_tag {
  background: rgba(171, 71, 188, 0.15);
  color: #ab47bc;
}

.suggestion-alias {
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}

.suggestion-category {
  font-size: 10px;
  color: var(--muted);
  margin-left: auto;
  opacity: 0.7;
}
</style>
