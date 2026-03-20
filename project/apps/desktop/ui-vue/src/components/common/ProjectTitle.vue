<template>
  <span
    v-if="!editing"
    class="project-path"
    :title="projectStore.projectDir"
    @dblclick="startEdit"
  >{{ displayName }}</span>
  <span v-else class="project-rename-inline">
    <input
      ref="inputRef"
      v-model="editValue"
      class="rename-input"
      :placeholder="L.project.projectNamePlaceholder"
      maxlength="100"
      @keydown.enter="save"
      @keydown.escape="cancel"
      @blur="save"
    />
  </span>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useProjectStore } from '../../stores/project.js'
import { useFormatters } from '../../composables/useFormatters.js'
import labels from '../../i18n/labels.js'

const L = labels
const projectStore = useProjectStore()
const { humanizeProjectDir } = useFormatters()

const editing = ref(false)
const editValue = ref('')
const inputRef = ref(null)

const displayName = computed(() => {
  if (projectStore.projectDisplayName) return projectStore.projectDisplayName
  if (!projectStore.projectDir) return L.project.noProject
  return humanizeProjectDir(projectStore.projectDir)
})

function startEdit() {
  if (!projectStore.projectDir) return
  editValue.value = displayName.value
  editing.value = true
  nextTick(() => {
    inputRef.value?.select()
  })
}

async function save() {
  if (!editing.value) return
  editing.value = false
  const v = editValue.value.trim()
  if (!v || v === displayName.value) return
  await projectStore.renameProject(v)
}

function cancel() {
  editing.value = false
}
</script>

<style scoped>
.project-rename-inline {
  display: inline-flex;
  align-items: center;
}
.rename-input {
  font-size: 12px;
  color: var(--text);
  background: var(--surface2);
  border: 1px solid var(--accent);
  border-radius: 4px;
  padding: 2px 6px;
  outline: none;
  min-width: 120px;
  max-width: 300px;
}
</style>
