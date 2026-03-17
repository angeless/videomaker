<template>
  <div class="canvas-view">
    <div class="canvas-placeholder">
      <div class="placeholder-icon">🧩</div>
      <h2>工作流画布</h2>
      <p class="placeholder-desc">
        类似 n8n 的可视化编排界面，可拖拽组合「选题」「粗剪」「配音」「发布」等能力节点，自定义自动化流水线。
      </p>
      <div class="placeholder-features">
        <div class="feature-item">
          <span class="feature-icon">🔗</span>
          <span>拖拽连线，自由组合能力</span>
        </div>
        <div class="feature-item">
          <span class="feature-icon">⚡</span>
          <span>一键运行，批量生产内容</span>
        </div>
        <div class="feature-item">
          <span class="feature-icon">📊</span>
          <span>实时查看每步执行状态</span>
        </div>
      </div>
      <p class="placeholder-status">开发中，敬请期待</p>
      <router-link to="/workflows" class="btn btn-primary" style="margin-top: 12px">
        前往工作流管理（列表模式）
      </router-link>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.canvas-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
}

.canvas-placeholder {
  text-align: center;
  color: var(--muted, #888);
  max-width: 420px;
}

.placeholder-icon {
  font-size: 56px;
  margin-bottom: 8px;
  opacity: 0.6;
}

.canvas-placeholder h2 {
  font-size: 20px;
  color: var(--text);
  margin-bottom: 8px;
}

.placeholder-desc {
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 20px;
}

.placeholder-features {
  display: flex;
  flex-direction: column;
  gap: 10px;
  text-align: left;
  margin-bottom: 20px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text);
  padding: 8px 12px;
  background: var(--surface2, rgba(255,255,255,0.04));
  border-radius: 8px;
}

.feature-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.placeholder-status {
  font-size: 11px;
  color: var(--muted);
  margin-top: 8px;
}
</style>
