<template>
  <div class="canvas-toolbar">
    <div class="toolbar-left">
      <input
        v-model="canvas.workflowName"
        class="toolbar-name-input"
        placeholder="工作流名称"
        @input="canvas.dirty = true"
      />
      <span v-if="canvas.dirty" class="toolbar-dirty">未保存</span>
      <span class="toolbar-stats">{{ canvas.nodeCount }} 个节点 · {{ canvas.edgeCount }} 条连接</span>
    </div>
    <div class="toolbar-right">
      <button class="btn btn-ghost btn-sm" :disabled="!canvas.canUndo" @click="canvas.undo()" title="撤销 (Ctrl+Z)">↩</button>
      <button class="btn btn-ghost btn-sm" :disabled="!canvas.canRedo" @click="canvas.redo()" title="重做 (Ctrl+Shift+Z)">↪</button>
      <button class="btn btn-ghost btn-sm" @click="canvas.resetView()">适应</button>
      <button class="btn btn-ghost btn-sm" @click="canvas.clear()">清空</button>
      <button
        class="btn btn-primary btn-sm"
        :disabled="canvas.saving || canvas.nodeCount === 0"
        @click="canvas.saveToBackend()"
      >
        {{ canvas.saving ? '保存中...' : '保存' }}
      </button>
      <button
        class="btn btn-success btn-sm"
        :disabled="canvas.running || !canvas.workflowId"
        @click="canvas.runWorkflow()"
      >
        {{ canvas.running ? '运行中...' : '运行' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { useCanvasStore } from '../../stores/canvas.js'

const canvas = useCanvasStore()
</script>

<style scoped>
.canvas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--surface, #1a1a2e);
  border-bottom: 1px solid var(--border, #333);
  flex-shrink: 0;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.toolbar-name-input {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
  padding: 4px 8px;
  width: 200px;
  outline: none;
  transition: border-color 0.15s;
}

.toolbar-name-input:hover,
.toolbar-name-input:focus {
  border-color: var(--border, #333);
}

.toolbar-dirty {
  font-size: 10px;
  color: var(--warn, #fbbf24);
  background: rgba(251, 191, 36, 0.1);
  padding: 1px 6px;
  border-radius: 3px;
}

.toolbar-stats {
  font-size: 11px;
  color: var(--muted, #888);
}

.toolbar-right {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
</style>
