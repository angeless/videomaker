<template>
  <div class="notification-wrapper" ref="wrapperRef">
    <button class="notification-bell" @click="open = !open" :title="bellTitle">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      </svg>
      <span v-if="store.unreadCount > 0" class="bell-badge">{{ store.unreadCount }}</span>
    </button>

    <div v-if="open" class="notification-dropdown">
      <div class="notification-header">
        <span>通知</span>
        <button v-if="store.items.length > 0" class="mark-all-btn" @click="store.markAllRead()">
          全部已读
        </button>
      </div>

      <div v-if="store.items.length === 0" class="notification-empty">
        暂无通知
      </div>

      <div v-else class="notification-list">
        <div
          v-for="n in store.items"
          :key="n.id"
          class="notification-item"
          :class="{ unread: !n.read, [`type-${n.type}`]: true }"
          @click="store.markRead(n.id)"
        >
          <div class="notification-dot" :class="`dot-${n.type}`"></div>
          <div class="notification-body">
            <div class="notification-msg">{{ n.message }}</div>
            <div class="notification-meta">{{ formatTime(n.timestamp) }}</div>
          </div>
          <button class="notification-dismiss" @click.stop="store.remove(n.id)" title="删除">&times;</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useNotificationsStore } from '../../stores/notifications.js'

const store = useNotificationsStore()
const open = ref(false)
const wrapperRef = ref(null)

const bellTitle = computed(() =>
  store.unreadCount > 0 ? `${store.unreadCount} 条未读通知` : '通知'
)

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function onClickOutside(e) {
  if (wrapperRef.value && !wrapperRef.value.contains(e.target)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.notification-wrapper {
  position: relative;
  margin-left: 8px;
}

.notification-bell {
  position: relative;
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  display: flex;
  align-items: center;
}

.notification-bell:hover {
  background: var(--surface2);
  color: var(--text);
}

.bell-badge {
  position: absolute;
  top: 2px;
  right: 0;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: #ff3b30;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.notification-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  width: 320px;
  max-height: 400px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  z-index: 1000;
  overflow: hidden;
}

.notification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  font-size: 13px;
}

.mark-all-btn {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 12px;
}

.notification-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.notification-list {
  max-height: 340px;
  overflow-y: auto;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.notification-item:hover {
  background: var(--surface2);
}

.notification-item.unread {
  background: rgba(90, 141, 238, 0.05);
}

.notification-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}

.dot-info { background: var(--accent); }
.dot-warn { background: #f0ad4e; }
.dot-danger { background: #ff3b30; }

.notification-body {
  flex: 1;
  min-width: 0;
}

.notification-msg {
  font-size: 13px;
  line-height: 1.4;
  word-break: break-word;
}

.notification-meta {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
}

.notification-dismiss {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 16px;
  padding: 0 4px;
  line-height: 1;
  flex-shrink: 0;
}

.notification-dismiss:hover {
  color: var(--text);
}
</style>
