<template>
  <div class="lhp2-panel">
    <div class="lhp2-header" @click="expanded = !expanded">
      <span class="lhp2-title">路径健康检查</span>
      <span class="lhp2-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-if="expanded" class="lhp2-body">
      <!-- 统计卡片（硬约束 5：使用真实后端口径 /fingerprint/health）-->
      <div v-if="store.locationHealthLoading" class="lhp2-loading">加载中...</div>
      <div v-else-if="store.locationHealth" class="lhp2-stats-grid">
        <div class="lhp2-stat-card">
          <div class="lhp2-stat-value">{{ store.locationHealth.total_assets }}</div>
          <div class="lhp2-stat-label">总素材</div>
        </div>
        <div class="lhp2-stat-card">
          <div class="lhp2-stat-value">{{ store.locationHealth.with_content_fingerprint }}</div>
          <div class="lhp2-stat-label">有指纹</div>
        </div>
        <div class="lhp2-stat-card">
          <div class="lhp2-stat-value">{{ store.locationHealth.duplicate_groups_total }}</div>
          <div class="lhp2-stat-label">重复组</div>
        </div>
        <div class="lhp2-stat-card">
          <div class="lhp2-stat-value">{{ store.locationHealth.total_path_changes }}</div>
          <div class="lhp2-stat-label">路径变更</div>
        </div>
      </div>

      <!-- 操作按钮（硬约束 1：所有面板必须可操作）-->
      <div class="lhp2-actions">
        <button
          class="btn btn-primary lhp2-btn"
          :disabled="store.locationScanLoading"
          @click="store.scanLocations()"
        >{{ store.locationScanLoading ? '扫描中...' : '扫描可用性' }}</button>
        <button
          class="btn btn-ghost lhp2-btn"
          :disabled="store.relocateLoading"
          @click="store.relocateLocations()"
        >{{ store.relocateLoading ? '重定位中...' : '批量重定位' }}</button>
      </div>

      <!-- 扫描结果（硬约束 2：操作完成后自动刷新）-->
      <div v-if="store.locationScanResult" class="lhp2-result">
        <div class="lhp2-result-title">扫描结果</div>
        <div class="lhp2-result-grid">
          <span class="lhp2-result-item">扫描 <b>{{ store.locationScanResult.scanned ?? '-' }}</b></span>
          <span class="lhp2-result-item lhp2-result-ok">可用 <b>{{ store.locationScanResult.available ?? '-' }}</b></span>
          <span class="lhp2-result-item lhp2-result-warn">不可用 <b>{{ store.locationScanResult.unavailable_count ?? store.locationScanResult.newly_unavailable ?? '-' }}</b></span>
        </div>
      </div>

      <!-- 重定位结果 -->
      <div v-if="store.relocateResult" class="lhp2-result">
        <div class="lhp2-result-title">重定位结果</div>
        <div class="lhp2-result-grid">
          <span class="lhp2-result-item">扫描 <b>{{ store.relocateResult.scanned ?? '-' }}</b></span>
          <span class="lhp2-result-item lhp2-result-ok">找回 <b>{{ store.relocateResult.relocated ?? '-' }}</b></span>
          <span class="lhp2-result-item lhp2-result-warn">失败 <b>{{ store.relocateResult.failed ?? '-' }}</b></span>
        </div>
      </div>

      <!-- 不可用素材列表 -->
      <div class="lhp2-unavailable-section">
        <div class="lhp2-unavailable-header" @click="showUnavailable = !showUnavailable">
          <span>不可用素材 ({{ store.unavailableAssets.length }})</span>
          <span class="lhp2-toggle">{{ showUnavailable ? '▾' : '▸' }}</span>
        </div>
        <div v-if="showUnavailable" class="lhp2-unavailable-body">
          <div v-if="store.unavailableLoading" class="lhp2-loading">加载中...</div>
          <div v-else-if="store.unavailableAssets.length === 0" class="lhp2-empty">所有路径均可用</div>
          <div v-else class="lhp2-unavailable-list">
            <div v-for="a in store.unavailableAssets" :key="a.id" class="lhp2-unavailable-item">
              <span class="lhp2-ua-name">{{ a.filename || a.uid }}</span>
              <span class="lhp2-ua-path" :title="a.path">{{ truncPath(a.path) }}</span>
              <span class="lhp2-ua-time">{{ a.last_seen_at || '-' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useLibraryStore } from '../../stores/library.js'

const store = useLibraryStore()
const expanded = ref(false)
const showUnavailable = ref(false)

function truncPath(p) {
  if (!p) return '-'
  return p.length > 60 ? '...' + p.slice(-57) : p
}

watch(expanded, (val) => {
  if (val) {
    store.fetchLocationHealth()
    store.fetchUnavailableLocations()
  }
})

watch(showUnavailable, (val) => {
  if (val && store.unavailableAssets.length === 0) {
    store.fetchUnavailableLocations()
  }
})
</script>

<style scoped>
.lhp2-panel {
  border: 1px solid var(--border); border-radius: 8px;
  margin-bottom: 16px; overflow: hidden;
}
.lhp2-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; cursor: pointer; background: var(--surface2); user-select: none;
}
.lhp2-header:hover { background: var(--surface3, rgba(255,255,255,0.06)); }
.lhp2-title { font-size: 13px; font-weight: 600; }
.lhp2-toggle { font-size: 12px; color: var(--muted); }
.lhp2-body { padding: 10px 12px; }
.lhp2-loading, .lhp2-empty { font-size: 12px; color: var(--muted); padding: 8px 0; text-align: center; }
.lhp2-stats-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px;
}
.lhp2-stat-card {
  background: var(--surface2); border-radius: 6px; padding: 10px;
  text-align: center; border: 1px solid var(--border);
}
.lhp2-stat-value { font-size: 18px; font-weight: 700; color: var(--accent); }
.lhp2-stat-label { font-size: 10px; color: var(--muted); margin-top: 2px; }
.lhp2-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.lhp2-btn { font-size: 12px; padding: 6px 14px; }
.lhp2-result {
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;
  margin-bottom: 10px; background: var(--surface2);
}
.lhp2-result-title { font-size: 11px; font-weight: 600; margin-bottom: 6px; }
.lhp2-result-grid { display: flex; gap: 16px; font-size: 12px; }
.lhp2-result-item { color: var(--muted); }
.lhp2-result-ok b { color: #4caf50; }
.lhp2-result-warn b { color: #ffb74d; }
.lhp2-unavailable-section {
  border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
}
.lhp2-unavailable-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; cursor: pointer; background: var(--surface2);
  font-size: 12px; font-weight: 500; user-select: none;
}
.lhp2-unavailable-header:hover { background: var(--surface3, rgba(255,255,255,0.06)); }
.lhp2-unavailable-body { max-height: 300px; overflow-y: auto; }
.lhp2-unavailable-list { padding: 4px 0; }
.lhp2-unavailable-item {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 10px; font-size: 11px; border-bottom: 1px solid rgba(255,255,255,0.04);
}
.lhp2-unavailable-item:last-child { border-bottom: none; }
.lhp2-ua-name { font-weight: 500; min-width: 120px; }
.lhp2-ua-path { flex: 1; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lhp2-ua-time { color: var(--muted); font-size: 10px; flex-shrink: 0; }
</style>
