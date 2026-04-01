<template>
  <div
    class="comment-card"
    :class="{ resolved: comment.status === 'resolved', nearby: isNearby }"
    :style="{ '--type-color': typeInfo.color }"
    @click="$emit('seek', comment.time_start_ms)"
  >
    <div class="cc-header">
      <span class="cc-type-badge" :style="{ background: typeInfo.color }">
        {{ typeInfo.icon }} {{ typeInfo.label }}
      </span>
      <span class="cc-time">{{ formatTime(comment.time_start_ms) }}</span>
      <span v-if="comment.time_end_ms" class="cc-time-range">
        → {{ formatTime(comment.time_end_ms) }}
      </span>
    </div>

    <p class="cc-text">{{ comment.text }}</p>

    <!-- Drawing thumbnail (if attached) -->
    <div v-if="comment.drawing_data" class="cc-drawing-badge" title="含标注">
      &#9998;
    </div>

    <div class="cc-footer">
      <span class="cc-version">v{{ comment.version }}</span>
      <span class="cc-status" :class="comment.status">
        {{ comment.status === 'resolved' ? '已处理' : '待处理' }}
      </span>
      <div class="cc-actions">
        <button
          v-if="comment.status !== 'resolved'"
          class="cc-action-btn"
          @click.stop="$emit('resolve', comment.id)"
          title="标记已处理"
        >✓</button>
        <button
          class="cc-action-btn cc-action-delete"
          @click.stop="$emit('delete', comment.id)"
          title="删除"
        >✕</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useReviewStore } from '../../stores/review.js'
import { COMMENT_TYPES } from '../../config/shortcuts.js'

const store = useReviewStore()

const props = defineProps({
  comment: { type: Object, required: true },
})

defineEmits(['seek', 'resolve', 'delete'])

const typeInfo = computed(() => {
  return COMMENT_TYPES.find(ct => ct.type === props.comment.comment_type) ||
    COMMENT_TYPES[COMMENT_TYPES.length - 1] // fallback to 'general'
})

const isNearby = computed(() => {
  const t = store.currentTimeMs
  const start = props.comment.time_start_ms
  return Math.abs(start - t) < 2000
})

function formatTime(ms) {
  if (!ms && ms !== 0) return ''
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m + ':' + String(sec).padStart(2, '0')
}
</script>

<style scoped>
.comment-card {
  background: #1e1e1e;
  border: 1px solid #333;
  border-left: 3px solid var(--type-color);
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.comment-card:hover {
  background: #252525;
}

.comment-card.nearby {
  background: #1e2530;
  border-color: #3b82f6;
}

.comment-card.resolved {
  opacity: 0.6;
}

.cc-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.cc-type-badge {
  font-size: 0.6rem;
  padding: 1px 6px;
  border-radius: 3px;
  color: #fff;
  white-space: nowrap;
}

.cc-time {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 0.65rem;
  color: #888;
}

.cc-time-range {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 0.65rem;
  color: #666;
}

.cc-text {
  font-size: 0.8rem;
  color: #ddd;
  line-height: 1.4;
  margin: 0;
  word-break: break-word;
}

.cc-drawing-badge {
  font-size: 0.7rem;
  color: #888;
  margin-top: 2px;
}

.cc-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.cc-version {
  font-size: 0.6rem;
  color: #555;
}

.cc-status {
  font-size: 0.6rem;
  padding: 1px 4px;
  border-radius: 2px;
}

.cc-status.pending {
  color: #eab308;
  background: rgba(234, 179, 8, 0.1);
}

.cc-status.resolved {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}

.cc-actions {
  margin-left: auto;
  display: flex;
  gap: 2px;
}

.cc-action-btn {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 0.7rem;
}

.cc-action-btn:hover {
  background: #333;
  color: #22c55e;
}

.cc-action-delete:hover {
  color: #ef4444;
}
</style>
