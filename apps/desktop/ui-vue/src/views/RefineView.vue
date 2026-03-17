<template>
  <div class="refine-view">
    <div class="view-header">
      <h2>{{ labels.createSidebar.refine }}</h2>
      <p class="view-desc">美颜、调色与精剪协作</p>
    </div>
    <div class="refine-content">
      <Refinement />
    </div>
  </div>
</template>

<script setup>
import labels from '../i18n/labels.js'
import Refinement from '../components/capabilities/Refinement.vue'
</script>

<style scoped>
.refine-view {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.view-header {
  margin-bottom: 20px;
  flex-shrink: 0;
}

.view-header h2 {
  margin: 0 0 4px 0;
  font-size: 18px;
}

.view-desc {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
}

.refine-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
</style>
