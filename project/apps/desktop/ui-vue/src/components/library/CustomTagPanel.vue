<template>
  <div class="custom-tag-panel">
    <div class="ctp-header" @click="expanded = !expanded">
      <span class="ctp-title">自定义标签</span>
      <span class="ctp-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-if="expanded" class="ctp-body">
      <!-- Create form -->
      <div class="ctp-form">
        <input
          v-model="newTagName"
          class="form-input ctp-input"
          placeholder="标签名称..."
          @keyup.enter="createTag"
        />
        <select v-model="newTagSlot" class="form-select ctp-select">
          <option value="">语义类型...</option>
          <option v-for="slot in semanticSlots" :key="slot" :value="slot">{{ slotLabel(slot) }}</option>
        </select>
        <button
          class="btn btn-primary ctp-btn"
          :disabled="!newTagName.trim() || creating"
          @click="createTag"
        >{{ creating ? '...' : '+创建' }}</button>
      </div>

      <div v-if="createMessage" class="ctp-message" :class="createMessageType">{{ createMessage }}</div>

      <!-- List existing custom tags -->
      <div v-if="loadingList" class="ctp-loading">加载中...</div>
      <div v-else-if="customTags.length > 0" class="ctp-list">
        <div v-for="ct in customTags" :key="ct.custom_tag_id" class="ctp-item">
          <span class="ctp-item-name" @click="$emit('search-tag', ct.custom_tag_name)">
            {{ ct.custom_tag_name }}
          </span>
          <span v-if="ct.semantic_slot" class="ctp-item-slot">{{ slotLabel(ct.semantic_slot) }}</span>
          <span class="ctp-item-status" :class="`status-${ct.status}`">{{ statusLabel(ct.status) }}</span>
          <span v-if="ct.match_count > 0" class="ctp-item-count">{{ ct.match_count }}次</span>
          <button
            class="ctp-item-del"
            title="归档"
            @click="archiveTag(ct.custom_tag_id)"
          >✕</button>
        </div>
      </div>
      <div v-else class="ctp-empty">暂无自定义标签</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useApiStore } from '../../stores/api.js'

const emit = defineEmits(['search-tag'])

const api = useApiStore()
const expanded = ref(false)

// Create form
const newTagName = ref('')
const newTagSlot = ref('')
const creating = ref(false)
const createMessage = ref('')
const createMessageType = ref('info')

// List
const customTags = ref([])
const loadingList = ref(false)

const semanticSlots = [
  'object', 'place', 'scene', 'action', 'person', 'event',
  'mood', 'style', 'weather', 'season', 'nature', 'food',
  'animal', 'indoor_outdoor', 'time_of_day', 'shot_type',
]

function slotLabel(slot) {
  const map = {
    object: '物体', place: '地点', scene: '场景', action: '动作',
    person: '人物', event: '事件', mood: '氛围', style: '风格',
    weather: '天气', season: '季节', nature: '自然', food: '美食',
    animal: '动物', indoor_outdoor: '室内外', time_of_day: '时段',
    shot_type: '镜头',
  }
  return map[slot] || slot
}

function statusLabel(status) {
  const map = { gray: '灰度', active: '活跃', review: '审核', archived: '已归档' }
  return map[status] || status
}

async function loadList() {
  loadingList.value = true
  const data = await api.api('GET', '/api/library/custom-tags')
  loadingList.value = false
  if (data.error) return
  customTags.value = data.custom_tags || []
}

async function createTag() {
  const name = newTagName.value.trim()
  if (!name) return
  creating.value = true
  createMessage.value = ''
  const body = { custom_tag_name: name }
  if (newTagSlot.value) body.semantic_slot = newTagSlot.value
  const data = await api.api('POST', '/api/library/custom-tags', body)
  creating.value = false
  if (data.error) {
    createMessage.value = data.error
    createMessageType.value = 'error'
    return
  }
  createMessage.value = `已创建 "${name}"`
  createMessageType.value = 'success'
  newTagName.value = ''
  newTagSlot.value = ''
  await loadList()
}

async function archiveTag(id) {
  const data = await api.api('DELETE', `/api/library/custom-tags/${id}`)
  if (data.error) {
    createMessage.value = data.error
    createMessageType.value = 'error'
    return
  }
  createMessage.value = '已归档'
  createMessageType.value = 'success'
  await loadList()
}

watch(expanded, (val) => {
  if (val && customTags.value.length === 0) {
    loadList()
  }
})
</script>

<style scoped>
.custom-tag-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
}

.ctp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  background: var(--surface2);
  user-select: none;
}

.ctp-header:hover {
  background: var(--surface3, rgba(255,255,255,0.06));
}

.ctp-title {
  font-size: 13px;
  font-weight: 600;
}

.ctp-toggle {
  font-size: 12px;
  color: var(--muted);
}

.ctp-body {
  padding: 10px 12px;
}

.ctp-form {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}

.ctp-input {
  flex: 1;
  font-size: 12px;
  padding: 5px 8px;
}

.ctp-select {
  font-size: 12px;
  padding: 5px 6px;
  width: 100px;
}

.ctp-btn {
  font-size: 11px;
  padding: 5px 10px;
  white-space: nowrap;
}

.ctp-message {
  font-size: 11px;
  margin-bottom: 8px;
  padding: 3px 6px;
  border-radius: 3px;
}

.ctp-message.success {
  color: #4caf50;
  background: rgba(76, 175, 80, 0.1);
}

.ctp-message.error {
  color: #ef5350;
  background: rgba(239, 83, 80, 0.1);
}

.ctp-loading,
.ctp-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 8px 0;
  text-align: center;
}

.ctp-list {
  max-height: 200px;
  overflow-y: auto;
}

.ctp-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px;
}

.ctp-item:last-child {
  border-bottom: none;
}

.ctp-item-name {
  font-weight: 500;
  cursor: pointer;
  flex: 1;
}

.ctp-item-name:hover {
  color: var(--accent);
}

.ctp-item-slot {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(90, 141, 238, 0.12);
  color: var(--accent);
}

.ctp-item-status {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}

.status-gray {
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted);
}

.status-active {
  background: rgba(76, 175, 80, 0.12);
  color: #4caf50;
}

.status-review {
  background: rgba(255, 183, 77, 0.15);
  color: #ffb74d;
}

.ctp-item-count {
  font-size: 10px;
  color: var(--muted);
}

.ctp-item-del {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 3px;
  transition: all 0.15s;
}

.ctp-item-del:hover {
  background: rgba(239, 83, 80, 0.15);
  color: #ef5350;
}
</style>
