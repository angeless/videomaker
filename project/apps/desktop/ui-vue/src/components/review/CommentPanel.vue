<template>
  <div class="comment-panel">
    <!-- Header with count + filter -->
    <div class="cp-header">
      <h3 class="cp-title">
        评审意见
        <span class="cp-count">{{ store.filteredComments.length }}</span>
        <span v-if="store.pendingComments.length" class="cp-pending">
          ({{ store.pendingComments.length }} 待处理)
        </span>
      </h3>
      <button class="cp-btn" @click="showFilters = !showFilters" title="筛选/排序">
        &#9776;
      </button>
    </div>

    <!-- Filter/Sort bar -->
    <div v-if="showFilters" class="cp-filters">
      <div class="cp-filter-row">
        <label class="cp-filter-label">类型</label>
        <select v-model="store.commentFilter.type" class="cp-select">
          <option :value="null">全部</option>
          <option v-for="ct in COMMENT_TYPES" :key="ct.type" :value="ct.type">
            {{ ct.icon }} {{ ct.label }}
          </option>
        </select>
      </div>
      <div class="cp-filter-row">
        <label class="cp-filter-label">状态</label>
        <select v-model="store.commentFilter.status" class="cp-select">
          <option :value="null">全部</option>
          <option value="pending">待处理</option>
          <option value="resolved">已处理</option>
        </select>
      </div>
      <div class="cp-filter-row">
        <label class="cp-filter-label">排序</label>
        <select v-model="store.commentSort" class="cp-select">
          <option value="time">时间</option>
          <option value="type">类型</option>
          <option value="status">状态</option>
        </select>
      </div>
    </div>

    <!-- Comment list -->
    <div class="cp-list" ref="listRef">
      <CommentCard
        v-for="comment in store.filteredComments"
        :key="comment.id"
        :comment="comment"
        @seek="onSeek"
        @resolve="onResolve"
        @delete="onDelete"
      />
      <div v-if="store.filteredComments.length === 0" class="cp-empty">
        <p>暂无评审意见</p>
        <p class="cp-empty-hint">按 C 或点击视频添加评审</p>
      </div>
    </div>

    <!-- Add comment button -->
    <button class="cp-add-btn" @click="openCommentInput" title="添加评审 (C)">
      + 添加评审
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useReviewStore } from '../../stores/review.js'
import { COMMENT_TYPES } from '../../config/shortcuts.js'
import CommentCard from './CommentCard.vue'

const store = useReviewStore()
const emit = defineEmits(['seek'])

const showFilters = ref(false)
const listRef = ref(null)

function onSeek(ms) {
  emit('seek', ms)
}

async function onResolve(commentId) {
  await store.resolveComment(commentId)
}

async function onDelete(commentId) {
  await store.deleteComment(commentId)
}

function openCommentInput() {
  store.enterCommentMode()
}
</script>

<style scoped>
.comment-panel {
  display: flex;
  flex-direction: column;
  background: #141414;
  border-left: 1px solid #333;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.cp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #333;
}

.cp-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: #eee;
  margin: 0;
}

.cp-count {
  font-size: 0.7rem;
  color: #888;
  font-weight: 400;
}

.cp-pending {
  font-size: 0.65rem;
  color: #eab308;
  font-weight: 400;
}

.cp-btn {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  padding: 4px;
  font-size: 0.8rem;
}

.cp-btn:hover {
  color: #fff;
}

/* Filters */
.cp-filters {
  padding: 8px 12px;
  border-bottom: 1px solid #333;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cp-filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cp-filter-label {
  font-size: 0.65rem;
  color: #888;
  min-width: 28px;
}

.cp-select {
  flex: 1;
  background: #2a2a2a;
  border: 1px solid #444;
  color: #ccc;
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 0.7rem;
}

/* List */
.cp-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cp-empty {
  text-align: center;
  padding: 24px 12px;
  color: #555;
  font-size: 0.8rem;
}

.cp-empty-hint {
  font-size: 0.7rem;
  color: #444;
  margin-top: 4px;
}

/* Add button */
.cp-add-btn {
  margin: 8px 12px;
  padding: 8px;
  background: #2a2a2a;
  border: 1px dashed #444;
  color: #888;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.75rem;
  transition: all 0.15s;
}

.cp-add-btn:hover {
  background: #333;
  border-color: #3b82f6;
  color: #3b82f6;
}
</style>
