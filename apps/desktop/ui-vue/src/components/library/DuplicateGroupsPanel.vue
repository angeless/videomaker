<template>
  <div class="dgp-panel">
    <div class="dgp-header" @click="expanded = !expanded">
      <span class="dgp-title">
        重复素材管理
        <span v-if="pendingCount > 0" class="dgp-badge dgp-badge-warn">{{ pendingCount }} 待处理</span>
      </span>
      <span class="dgp-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-if="expanded" class="dgp-body">
      <!-- 工具栏 -->
      <div class="dgp-toolbar">
        <select v-model="store.duplicateStatusFilter" class="form-select dgp-select" @change="store.fetchDuplicateGroups()">
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="resolved">已解决</option>
          <option value="ignored">已忽略</option>
        </select>
        <button class="btn btn-primary dgp-btn" :disabled="store.duplicateGroupsLoading" @click="store.detectDuplicates()">
          {{ store.duplicateGroupsLoading ? '检测中...' : '检测重复' }}
        </button>
        <button class="btn btn-ghost dgp-btn" :disabled="store.duplicateGroupsLoading" @click="store.fetchDuplicateGroups()">
          刷新
        </button>
      </div>

      <!-- 加载 / 空态 -->
      <div v-if="store.duplicateGroupsLoading" class="dgp-loading">检测中...</div>
      <div v-else-if="store.duplicateGroups.length === 0" class="dgp-empty">暂无重复组</div>

      <!-- 重复组列表 -->
      <div v-else class="dgp-list">
        <div v-for="group in store.duplicateGroups" :key="group.group_id" class="dgp-group">
          <!-- 组头 -->
          <div class="dgp-group-head">
            <span class="dgp-type-badge" :class="`dgp-type-${group.group_type}`">{{ typeLabel(group.group_type) }}</span>
            <span class="dgp-meta">{{ group.member_count }} 个文件</span>
            <span class="dgp-meta">{{ formatBytes(group.total_size_bytes) }}</span>
            <span class="dgp-status-badge" :class="`dgp-status-${group.status}`">{{ statusLabel(group.status) }}</span>
          </div>

          <!-- 成员列表（硬约束 4：明确显示主文件和 keep/remove 状态）-->
          <div class="dgp-members">
            <div v-for="m in group.members" :key="m.id" class="dgp-member" :class="{ 'dgp-member-primary': group.primary_uid === m.uid }">
              <div class="dgp-member-info">
                <span class="dgp-member-name">
                  {{ m.filename || m.uid }}
                  <span v-if="group.primary_uid === m.uid" class="dgp-primary-tag">主文件</span>
                </span>
                <span class="dgp-member-path" :title="m.primary_path">{{ truncPath(m.primary_path) }}</span>
                <span class="dgp-member-detail">
                  <span v-if="m.fingerprint_distance > 0">距离 {{ m.fingerprint_distance }}</span>
                  <span v-if="m.resolution">{{ m.resolution }}</span>
                  <span v-if="m.file_size">{{ formatBytes(m.file_size) }}</span>
                </span>
              </div>
              <div class="dgp-member-actions">
                <!-- keep/remove 决策按钮（硬约束 4）-->
                <button
                  class="dgp-decision-btn"
                  :class="{ active: m.keep_decision === 'keep' }"
                  title="保留"
                  @click="store.setDuplicateMemberDecision(group.group_id, m.id, m.keep_decision === 'keep' ? 'undecided' : 'keep')"
                >✓保留</button>
                <button
                  class="dgp-decision-btn dgp-decision-remove"
                  :class="{ active: m.keep_decision === 'remove' }"
                  title="移除"
                  @click="store.setDuplicateMemberDecision(group.group_id, m.id, m.keep_decision === 'remove' ? 'undecided' : 'remove')"
                >✕移除</button>
                <button
                  v-if="group.primary_uid !== m.uid"
                  class="dgp-decision-btn dgp-decision-primary"
                  title="设为主文件"
                  @click="store.setDuplicatePrimary(group.group_id, m.uid)"
                >★主文件</button>
              </div>
            </div>
          </div>

          <!-- 组操作 -->
          <div class="dgp-group-actions">
            <button v-if="group.status === 'pending'" class="btn btn-sm dgp-resolve-btn" @click="store.resolveDuplicateGroup(group.group_id)">标为已解决</button>
            <button v-if="group.status === 'pending'" class="btn btn-sm btn-ghost" @click="store.ignoreDuplicateGroup(group.group_id)">忽略</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useLibraryStore } from '../../stores/library.js'

const store = useLibraryStore()
const expanded = ref(false)

const pendingCount = computed(() =>
  store.duplicateGroups.filter(g => g.status === 'pending').length
)

const typeLabels = {
  exact_sha: '完全相同',
  near_identical: '近似相同',
  very_similar: '非常相似',
  similar: '相似',
}
function typeLabel(t) { return typeLabels[t] || t }

const statusLabels = { pending: '待处理', resolved: '已解决', ignored: '已忽略' }
function statusLabel(s) { return statusLabels[s] || s }

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++ }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

function truncPath(p) {
  if (!p) return '-'
  return p.length > 50 ? '...' + p.slice(-47) : p
}

watch(expanded, (val) => {
  if (val) store.fetchDuplicateGroups()
})
</script>

<style scoped>
.dgp-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
}
.dgp-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; cursor: pointer; background: var(--surface2); user-select: none;
}
.dgp-header:hover { background: var(--surface3, rgba(255,255,255,0.06)); }
.dgp-title { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.dgp-toggle { font-size: 12px; color: var(--muted); }
.dgp-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; }
.dgp-badge-warn { background: rgba(255,183,77,0.18); color: #ffb74d; }
.dgp-body { padding: 10px 12px; }
.dgp-toolbar { display: flex; gap: 6px; align-items: center; margin-bottom: 10px; }
.dgp-select { font-size: 12px; padding: 5px 6px; width: 110px; }
.dgp-btn { font-size: 11px; padding: 5px 10px; }
.dgp-loading, .dgp-empty { font-size: 12px; color: var(--muted); padding: 12px 0; text-align: center; }
.dgp-list { max-height: 500px; overflow-y: auto; }
.dgp-group { border: 1px solid var(--border); border-radius: 6px; margin-bottom: 10px; overflow: hidden; }
.dgp-group-head {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; background: var(--surface2); font-size: 12px;
}
.dgp-type-badge { font-size: 10px; padding: 1px 6px; border-radius: 4px; font-weight: 600; }
.dgp-type-exact_sha { background: rgba(239,83,80,0.15); color: #ef5350; }
.dgp-type-near_identical { background: rgba(255,183,77,0.15); color: #ffb74d; }
.dgp-type-very_similar { background: rgba(90,141,238,0.15); color: var(--accent); }
.dgp-type-similar { background: rgba(255,255,255,0.08); color: var(--muted); }
.dgp-meta { font-size: 11px; color: var(--muted); }
.dgp-status-badge { font-size: 10px; padding: 1px 5px; border-radius: 3px; margin-left: auto; }
.dgp-status-pending { background: rgba(255,183,77,0.15); color: #ffb74d; }
.dgp-status-resolved { background: rgba(76,175,80,0.15); color: #4caf50; }
.dgp-status-ignored { background: rgba(255,255,255,0.06); color: var(--muted); }
.dgp-members { padding: 4px 0; }
.dgp-member {
  display: flex; align-items: center; justify-content: space-between;
  padding: 5px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); gap: 8px;
}
.dgp-member:last-child { border-bottom: none; }
.dgp-member-primary { background: rgba(76,175,80,0.06); }
.dgp-member-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.dgp-member-name { font-size: 12px; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.dgp-primary-tag {
  font-size: 9px; padding: 0px 4px; border-radius: 3px;
  background: rgba(76,175,80,0.2); color: #4caf50; font-weight: 600;
}
.dgp-member-path { font-size: 10px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dgp-member-detail { font-size: 10px; color: var(--muted); display: flex; gap: 8px; }
.dgp-member-actions { display: flex; gap: 4px; flex-shrink: 0; }
.dgp-decision-btn {
  font-size: 10px; padding: 2px 6px; border-radius: 3px; border: 1px solid var(--border);
  background: none; color: var(--muted); cursor: pointer; transition: all 0.15s;
}
.dgp-decision-btn:hover { border-color: var(--accent); color: var(--accent); }
.dgp-decision-btn.active { background: rgba(76,175,80,0.15); color: #4caf50; border-color: #4caf50; }
.dgp-decision-remove.active { background: rgba(239,83,80,0.15); color: #ef5350; border-color: #ef5350; }
.dgp-decision-primary { color: var(--accent); border-color: transparent; }
.dgp-decision-primary:hover { border-color: var(--accent); }
.dgp-group-actions { display: flex; gap: 6px; padding: 6px 10px; border-top: 1px solid rgba(255,255,255,0.04); }
.dgp-resolve-btn { background: rgba(76,175,80,0.15); color: #4caf50; border: none; }
.dgp-resolve-btn:hover { background: rgba(76,175,80,0.25); }
</style>
