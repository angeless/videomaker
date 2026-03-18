<template>
  <aside class="node-palette">
    <div class="palette-title">能力节点</div>
    <input
      v-model="filter"
      class="palette-search"
      placeholder="搜索能力…"
    />
    <div v-for="group in filteredGroups" :key="group.key" class="palette-group">
      <div class="palette-group-title">{{ group.title }}</div>
      <div
        v-for="item in group.items"
        :key="item.tab"
        class="palette-item"
        draggable="true"
        @dragstart="onDragStart($event, item)"
      >
        <span class="palette-item-icon">{{ iconFor(item.tab) }}</span>
        <span class="palette-item-label">{{ item.label }}</span>
      </div>
    </div>
    <div v-if="filteredGroups.length === 0" class="palette-empty">无匹配节点</div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useCapabilitiesStore } from '../../stores/capabilities.js'

const capStore = useCapabilitiesStore()
const filter = ref('')

const filteredGroups = computed(() => {
  const groups = capStore.groups || []
  const q = filter.value.trim().toLowerCase()
  if (!q) return groups
  return groups
    .map(g => ({
      ...g,
      items: (g.items || []).filter(i => (i.label || '').toLowerCase().includes(q) || (i.tab || '').includes(q)),
    }))
    .filter(g => g.items.length > 0)
})

const icons = {
  topic_library: '💡', topic_copy: '📝', article_expand: '📰',
  text_rough: '✂️', short_clip: '⚡', refinement: '✨',
  audio_voice: '🎵', subtitle_calibration: '📋', image_semantic: '🖼️',
  publish_prep: '📤', social_export: '🌐', content_publish: '🚀',
}

function iconFor(tab) {
  return icons[tab] || '🔧'
}

function onDragStart(e, item) {
  e.dataTransfer.setData('application/canvas-node', JSON.stringify({
    capability_id: item.tab,
    label: item.label,
  }))
  e.dataTransfer.effectAllowed = 'copy'
}
</script>

<style scoped>
.node-palette {
  width: 180px;
  flex-shrink: 0;
  background: var(--surface, #1a1a2e);
  border-right: 1px solid var(--border, #333);
  overflow-y: auto;
  padding: 12px 0;
}

.palette-title {
  font-size: 13px;
  font-weight: 600;
  padding: 0 12px 4px;
  color: var(--text);
}

.palette-search {
  width: calc(100% - 24px);
  margin: 0 12px 8px;
  padding: 5px 8px;
  font-size: 12px;
  background: var(--bg, #111);
  border: 1px solid var(--border, #333);
  border-radius: 5px;
  color: var(--text);
  outline: none;
}

.palette-search:focus {
  border-color: var(--accent, #5a8dee);
}

.palette-empty {
  font-size: 11px;
  color: var(--muted, #888);
  padding: 12px;
  text-align: center;
}

.palette-group {
  margin-bottom: 8px;
}

.palette-group-title {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--muted, #888);
  padding: 6px 12px 2px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.palette-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: grab;
  font-size: 12px;
  color: var(--text);
  transition: background 0.12s;
  user-select: none;
}

.palette-item:hover {
  background: var(--surface2, rgba(255,255,255,0.06));
}

.palette-item:active {
  cursor: grabbing;
  opacity: 0.7;
}

.palette-item-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.palette-item-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
