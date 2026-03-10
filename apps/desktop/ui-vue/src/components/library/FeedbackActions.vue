<template>
  <div class="feedback-actions">
    <!-- Per-tag confirm / reject -->
    <div v-if="tagId" class="feedback-tag-actions">
      <span class="fb-label">{{ tagName || '标签' }}</span>
      <button
        class="fb-btn fb-confirm"
        :class="{ active: confirmState === 'confirmed' }"
        :disabled="submitting"
        @click="doFeedback('confirm_correct')"
        title="确认正确"
      >✓</button>
      <button
        class="fb-btn fb-reject"
        :class="{ active: confirmState === 'rejected' }"
        :disabled="submitting"
        @click="doFeedback('reject_wrong')"
        title="标记错误"
      >✗</button>
      <button
        class="fb-btn fb-remove"
        :disabled="submitting"
        @click="doFeedback('remove_irrelevant')"
        title="移除无关"
      >🗑</button>
    </div>

    <!-- Add missing tag -->
    <div class="feedback-add">
      <input
        v-model="addTagInput"
        class="fb-input"
        placeholder="添加缺失标签..."
        @keyup.enter="doAddMissing"
      />
      <button
        class="fb-btn fb-add"
        :disabled="!addTagInput.trim() || submitting"
        @click="doAddMissing"
      >+添加</button>
    </div>

    <div v-if="message" class="fb-message" :class="messageType">{{ message }}</div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useApiStore } from '../../stores/api.js'

const props = defineProps({
  assetId: { type: String, required: true },
  tagId: { type: [Number, null], default: null },
  tagName: { type: String, default: '' },
  confirmState: { type: String, default: 'none' },
})

const emit = defineEmits(['feedback-done'])

const api = useApiStore()
const submitting = ref(false)
const message = ref('')
const messageType = ref('info')
const addTagInput = ref('')

async function doFeedback(feedbackType) {
  submitting.value = true
  message.value = ''
  const data = {
    asset_id: props.assetId,
    feedback_type: feedbackType,
    tag_id: props.tagId,
  }
  const result = await api.api('POST', '/api/library/feedback', data)
  submitting.value = false
  if (result.error) {
    message.value = result.error
    messageType.value = 'error'
    return
  }
  const labels = {
    confirm_correct: '已确认',
    reject_wrong: '已标记错误',
    remove_irrelevant: '已移除',
  }
  message.value = labels[feedbackType] || '已提交'
  messageType.value = 'success'
  emit('feedback-done', { feedbackType, tagId: props.tagId })
}

async function doAddMissing() {
  const tagName = addTagInput.value.trim()
  if (!tagName) return
  submitting.value = true
  message.value = ''
  const data = {
    asset_id: props.assetId,
    feedback_type: 'add_missing',
    tag_name: tagName,
  }
  const result = await api.api('POST', '/api/library/feedback', data)
  submitting.value = false
  if (result.error) {
    message.value = result.error
    messageType.value = 'error'
    return
  }
  message.value = `已添加 "${tagName}"`
  messageType.value = 'success'
  addTagInput.value = ''
  emit('feedback-done', { feedbackType: 'add_missing', tagName })
}
</script>

<style scoped>
.feedback-actions {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(255,255,255,0.06);
}

.feedback-tag-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.fb-label {
  font-size: 12px;
  font-weight: 500;
  margin-right: 4px;
}

.fb-btn {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--muted);
}

.fb-btn:hover:not(:disabled) {
  background: var(--surface2);
}

.fb-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.fb-confirm.active {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
  border-color: #4caf50;
}

.fb-reject.active {
  background: rgba(239, 83, 80, 0.2);
  color: #ef5350;
  border-color: #ef5350;
}

.feedback-add {
  display: flex;
  gap: 6px;
  align-items: center;
}

.fb-input {
  flex: 1;
  font-size: 12px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: inherit;
}

.fb-input::placeholder {
  color: var(--muted);
}

.fb-add {
  font-size: 11px;
  white-space: nowrap;
  color: var(--accent);
  border-color: var(--accent);
}

.fb-message {
  font-size: 11px;
  margin-top: 6px;
  padding: 3px 6px;
  border-radius: 3px;
}

.fb-message.success {
  color: #4caf50;
  background: rgba(76, 175, 80, 0.1);
}

.fb-message.error {
  color: #ef5350;
  background: rgba(239, 83, 80, 0.1);
}

.fb-message.info {
  color: var(--muted);
}
</style>
