<template>
  <div>
    <h3>{{ labels.tools.items[tab]?.label || tab }}</h3>
    <p class="text-muted" style="margin-bottom: 16px">
      {{ labels.tools.items[tab]?.hint || '' }}
    </p>
    <div class="empty-state" style="padding: 32px">
      <div class="empty-state-icon">🔧</div>
      <div class="empty-state-text">
        此功能正在迁移中，即将上线。
      </div>
    </div>
  </div>
</template>

<script setup>
import labels from '../../i18n/labels.js'

defineProps({
  tab: { type: String, default: 'topic_library' },
})
</script>

<style scoped>
h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}
</style>
