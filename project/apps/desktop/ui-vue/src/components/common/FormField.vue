<template>
  <div class="form-field" :class="{ 'has-error': !!error }">
    <label v-if="label" class="form-label" :for="fieldId">{{ label }}</label>
    <slot />
    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-else-if="hint" class="form-hint">{{ hint }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, default: '' },
  error: { type: String, default: '' },
  hint: { type: String, default: '' },
  fieldId: { type: String, default: '' },
})
</script>

<style scoped>
.form-field {
  margin-bottom: 12px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--text);
}

.form-error {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #ff3b30;
}

.has-error :deep(input),
.has-error :deep(select),
.has-error :deep(textarea) {
  border-color: #ff3b30;
}
</style>
