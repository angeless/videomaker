<template>
  <div class="scene-selector">
    <div class="ss-header">
      <span class="ss-title">场景选择</span>
      <span class="ss-count text-muted">{{ selectedCount }}/{{ scenes.length }} 已选</span>
      <div class="ss-actions">
        <button class="btn btn-ghost btn-xs" @click="store.selectAllScenes()">全选</button>
        <button class="btn btn-ghost btn-xs" @click="store.deselectAllScenes()">全不选</button>
        <button class="btn btn-primary btn-xs" @click="submitSelection" :disabled="!selectedCount">
          确认选择
        </button>
      </div>
    </div>

    <div v-if="!scenes.length" class="ss-empty text-muted">
      暂无场景数据。
    </div>

    <div v-else class="ss-grid">
      <div
        v-for="scene in scenes"
        :key="scene.scene_idx"
        class="ss-card"
        :class="{ selected: scene.selected }"
        @click="store.toggleScene(scene.scene_idx)"
      >
        <!-- Thumbnail placeholder -->
        <div class="ss-thumb">
          <img v-if="scene.thumbnail_path" :src="scene.thumbnail_path" alt="" />
          <div v-else class="ss-thumb-placeholder">{{ scene.scene_idx + 1 }}</div>
        </div>
        <div class="ss-info">
          <span class="ss-time">{{ formatTime(scene.start_ms) }} - {{ formatTime(scene.end_ms) }}</span>
          <span class="ss-dur text-muted">{{ ((scene.duration_ms || 0) / 1000).toFixed(1) }}s</span>
        </div>
        <div class="ss-check">{{ scene.selected ? '✓' : '' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoughcutStore } from '../../stores/roughcut.js'

const store = useRoughcutStore()
const scenes = computed(() => store.scenes)
const selectedCount = computed(() => store.selectedScenes.length)

async function submitSelection() {
  await store.submitSceneSelection()
}

function formatTime(ms) {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.scene-selector {
  background: var(--bg-panel, #1a1a2e);
  border-radius: 8px;
  overflow: hidden;
}
.ss-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
}
.ss-title { font-weight: 600; font-size: 14px; }
.ss-actions { margin-left: auto; display: flex; gap: 4px; }
.ss-empty { padding: 24px; text-align: center; font-size: 13px; }
.ss-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  padding: 12px;
  max-height: 300px;
  overflow-y: auto;
}
.ss-card {
  border: 2px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.1s;
  overflow: hidden;
  background: var(--bg-card, rgba(255,255,255,0.04));
}
.ss-card:hover { border-color: rgba(59,130,246,0.3); }
.ss-card.selected { border-color: #3b82f6; }
.ss-thumb { aspect-ratio: 16/9; background: #0f0f1a; display: flex; align-items: center; justify-content: center; }
.ss-thumb img { width: 100%; height: 100%; object-fit: cover; }
.ss-thumb-placeholder { font-size: 20px; font-weight: 700; color: #4b5563; }
.ss-info { padding: 4px 8px; font-size: 11px; display: flex; justify-content: space-between; }
.ss-check { text-align: center; font-size: 14px; color: #3b82f6; padding-bottom: 4px; min-height: 20px; }
</style>
