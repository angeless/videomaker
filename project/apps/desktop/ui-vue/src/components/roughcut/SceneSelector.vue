<template>
  <div class="scene-selector">
    <div class="ss-header">
      <span class="ss-title">场景选择</span>
      <span class="ss-count text-muted">{{ selectedCount }}/{{ scenes.length }} 已选</span>
      <div class="ss-actions">
        <button class="btn btn-ghost btn-xs" @click="store.selectAllScenes()">全选</button>
        <button class="btn btn-ghost btn-xs" @click="store.deselectAllScenes()">全不选</button>
        <button class="btn btn-accent btn-xs" @click="aiAutoSelect" :disabled="!scenes.length">
          AI 自动选择
        </button>
        <button class="btn btn-primary btn-xs" @click="submitSelection" :disabled="!selectedCount">
          生成粗剪
        </button>
      </div>
    </div>

    <!-- Filter + Sort bar -->
    <div class="ss-toolbar" v-if="scenes.length">
      <div class="ss-filters">
        <button
          v-for="f in filterOptions"
          :key="f.value"
          class="btn btn-ghost btn-xs"
          :class="{ active: activeFilter === f.value }"
          @click="activeFilter = f.value"
        >{{ f.label }}</button>
      </div>
      <div class="ss-sort">
        <select v-model="sortBy" class="ss-select">
          <option value="time">时间顺序</option>
          <option value="duration">时长</option>
          <option value="quality">质量评分</option>
          <option value="ai">AI 推荐</option>
        </select>
      </div>
      <div class="ss-target">
        <select v-model="targetDuration" class="ss-select">
          <option :value="0">不限时长</option>
          <option :value="30">30s</option>
          <option :value="60">60s</option>
          <option :value="90">90s</option>
        </select>
      </div>
    </div>

    <div v-if="!scenes.length" class="ss-empty text-muted">
      暂无场景数据。
    </div>

    <div v-else class="ss-grid">
      <div
        v-for="scene in filteredAndSorted"
        :key="scene.scene_idx"
        class="ss-card"
        :class="{ selected: scene.selected }"
        @click="store.toggleScene(scene.scene_idx)"
      >
        <!-- Thumbnail -->
        <div class="ss-thumb">
          <img v-if="scene.thumbnail_path" :src="scene.thumbnail_path" alt="" />
          <div v-else class="ss-thumb-placeholder">{{ scene.scene_idx + 1 }}</div>
          <span v-if="scene.scene_type" class="ss-type-badge">{{ scene.scene_type }}</span>
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
import { ref, computed } from 'vue'
import { useRoughcutStore } from '../../stores/roughcut.js'

const store = useRoughcutStore()
const scenes = computed(() => store.scenes)
const selectedCount = computed(() => store.selectedScenes.length)

// ── Filter ──
const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '风景', value: 'landscape' },
  { label: '人物', value: 'person' },
  { label: '动作', value: 'action' },
  { label: '静物', value: 'static' },
  { label: '特写', value: 'closeup' },
]
const activeFilter = ref('all')

// ── Sort ──
const sortBy = ref('time')

// ── Target duration ──
const targetDuration = ref(0)

const filteredAndSorted = computed(() => {
  let result = [...scenes.value]

  // Filter by scene_type
  if (activeFilter.value !== 'all') {
    result = result.filter(s => s.scene_type === activeFilter.value)
  }

  // Sort
  if (sortBy.value === 'duration') {
    result.sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0))
  } else if (sortBy.value === 'quality') {
    result.sort((a, b) => (b.quality_score || 0) - (a.quality_score || 0))
  } else if (sortBy.value === 'ai') {
    result.sort((a, b) => (b.ai_score || 0) - (a.ai_score || 0))
  } else {
    result.sort((a, b) => a.start_ms - b.start_ms)
  }

  return result
})

// ── AI auto-select ──
function aiAutoSelect() {
  store.deselectAllScenes()

  // Sort by ai_score (or quality_score fallback), pick scenes until target duration
  const ranked = [...scenes.value].sort(
    (a, b) => (b.ai_score || b.quality_score || 0) - (a.ai_score || a.quality_score || 0)
  )

  const target = targetDuration.value > 0 ? targetDuration.value * 1000 : Infinity
  let totalMs = 0

  for (const scene of ranked) {
    const dur = scene.duration_ms || 0
    if (totalMs + dur > target && totalMs > 0) continue
    store.toggleScene(scene.scene_idx)
    totalMs += dur
    if (totalMs >= target) break
  }
}

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

.ss-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
  flex-wrap: wrap;
}
.ss-filters { display: flex; gap: 2px; }
.ss-filters .btn.active { background: rgba(59,130,246,0.2); color: #60a5fa; }
.ss-sort, .ss-target { margin-left: auto; }
.ss-select {
  background: rgba(255,255,255,0.06);
  color: #ccc;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
}

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
.ss-thumb {
  position: relative;
  aspect-ratio: 16/9;
  background: #0f0f1a;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ss-thumb img { width: 100%; height: 100%; object-fit: cover; }
.ss-thumb-placeholder { font-size: 20px; font-weight: 700; color: #4b5563; }
.ss-type-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(0,0,0,0.7);
  color: #aaa;
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
}
.ss-info { padding: 4px 8px; font-size: 11px; display: flex; justify-content: space-between; }
.ss-check { text-align: center; font-size: 14px; color: #3b82f6; padding-bottom: 4px; min-height: 20px; }
</style>
