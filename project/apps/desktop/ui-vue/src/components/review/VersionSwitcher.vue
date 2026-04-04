<template>
  <div class="version-switcher">
    <button
      class="vs-btn"
      :disabled="store.currentVersion <= 1"
      @click="switchVersion(store.currentVersion - 1)"
      title="上一版本 (Cmd+[)"
    >&#9664;</button>

    <div class="vs-label">
      <span class="vs-current">V{{ store.currentVersion }}</span>
      <span class="vs-total" v-if="store.versions.length">/ {{ store.versions.length }}</span>
    </div>

    <button
      class="vs-btn"
      :disabled="store.currentVersion >= store.versions.length"
      @click="switchVersion(store.currentVersion + 1)"
      title="下一版本 (Cmd+])"
    >&#9654;</button>

    <!-- Dropdown for direct version jump -->
    <div class="vs-dropdown" v-if="showDropdown">
      <div
        v-for="v in store.versions"
        :key="v.version_number"
        class="vs-dropdown-item"
        :class="{ active: v.version_number === store.currentVersion }"
        @click="switchVersion(v.version_number); showDropdown = false"
      >
        <span class="vs-v-num">V{{ v.version_number }}</span>
        <span class="vs-v-date">{{ formatDate(v.created_at) }}</span>
        <span class="vs-v-comments" v-if="v.comment_count != null">
          {{ v.comment_count }} 条
        </span>
      </div>
    </div>

    <button
      class="vs-btn vs-btn-expand"
      @click="showDropdown = !showDropdown"
      title="版本列表"
    >▾</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()
const showDropdown = ref(false)

async function switchVersion(num) {
  if (num < 1 || num > store.versions.length) return
  await store.switchVersion(num)
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return (d.getMonth() + 1) + '/' + d.getDate() + ' ' +
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0')
}
</script>

<style scoped>
.version-switcher {
  display: flex;
  align-items: center;
  gap: 4px;
  position: relative;
}

.vs-btn {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 0.65rem;
  border-radius: 3px;
}

.vs-btn:hover:not(:disabled) {
  background: #333;
  color: #fff;
}

.vs-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.vs-label {
  font-size: 0.75rem;
  color: #ccc;
  min-width: 40px;
  text-align: center;
}

.vs-current {
  font-weight: 600;
}

.vs-total {
  color: #666;
  font-size: 0.65rem;
}

.vs-btn-expand {
  font-size: 0.6rem;
  padding: 2px 4px;
}

/* Dropdown */
.vs-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  min-width: 160px;
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 4px;
  z-index: 30;
  max-height: 200px;
  overflow-y: auto;
}

.vs-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.7rem;
  color: #ccc;
}

.vs-dropdown-item:hover {
  background: #2a2a2a;
}

.vs-dropdown-item.active {
  background: #1e3a5f;
  color: #3b82f6;
}

.vs-v-num {
  font-weight: 600;
  min-width: 24px;
}

.vs-v-date {
  color: #666;
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 0.6rem;
}

.vs-v-comments {
  margin-left: auto;
  color: #555;
  font-size: 0.6rem;
}
</style>
