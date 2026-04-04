<template>
  <span
    class="filler-markup"
    :class="[type, { preview: isPreviewing }]"
    :title="label"
    @click.stop="togglePreview"
    @mouseenter="$emit('hover', word)"
    @mouseleave="$emit('unhover')"
  >
    <span class="fm-text">{{ word.text }}</span>
    <span v-if="showBadge" class="fm-badge">{{ badgeText }}</span>
  </span>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  word: { type: Object, required: true },
  type: {
    type: String,
    default: 'filler',
    validator: (v) => ['filler', 'retake', 'silence'].includes(v),
  },
  showBadge: { type: Boolean, default: false },
})

const emit = defineEmits(['seek', 'hover', 'unhover'])

const isPreviewing = ref(false)

const label = computed(() => {
  const labels = { filler: '语气词', retake: '重复片段', silence: '静音' }
  return labels[props.type] || props.type
})

const badgeText = computed(() => {
  const badges = { filler: '嗯', retake: '重', silence: '…' }
  return badges[props.type] || ''
})

function togglePreview() {
  isPreviewing.value = !isPreviewing.value
  if (props.word.start_ms != null) {
    emit('seek', props.word.start_ms)
  }
}
</script>

<style scoped>
.filler-markup {
  display: inline;
  padding: 0 2px;
  border-radius: 2px;
  cursor: pointer;
  position: relative;
  transition: background 0.15s;
}

.filler-markup.filler {
  background: rgba(239, 68, 68, 0.2);
  color: #fca5a5;
}
.filler-markup.retake {
  background: rgba(245, 158, 11, 0.2);
  color: #fcd34d;
}
.filler-markup.silence {
  background: rgba(107, 114, 128, 0.2);
  color: #9ca3af;
}

.filler-markup.preview {
  outline: 1px solid currentColor;
  outline-offset: 1px;
}

.filler-markup:hover {
  filter: brightness(1.2);
}

.fm-badge {
  font-size: 9px;
  vertical-align: super;
  opacity: 0.7;
  margin-left: 1px;
}
</style>
