<template>
  <div class="titlebar">
    <span class="title">{{ labels.appTitle }}</span>
    <span class="project-path">{{ appStore.projectDir || '未打开项目' }}</span>
    <AppNav />
  </div>

  <div class="main">
    <div class="content">
      <div class="content-narrow">
        <!-- 搜索栏 -->
        <div class="library-toolbar">
          <div class="search-box">
            <input
              v-model="libraryStore.query"
              class="form-input"
              :placeholder="labels.library.search"
              @keyup.enter="libraryStore.search()"
            />
          </div>
          <div class="toolbar-controls">
            <select v-model="libraryStore.searchMode" class="form-select" style="width: 120px">
              <option value="hybrid">{{ labels.library.searchMode.hybrid }}</option>
              <option value="keyword">{{ labels.library.searchMode.keyword }}</option>
              <option value="vector">{{ labels.library.searchMode.vector }}</option>
            </select>
            <select v-model="libraryStore.mediaType" class="form-select" style="width: 90px">
              <option value="all">{{ labels.library.mediaType.all }}</option>
              <option value="video">{{ labels.library.mediaType.video }}</option>
              <option value="image">{{ labels.library.mediaType.image }}</option>
            </select>
            <!-- 视图切换 -->
            <div class="view-toggle">
              <button
                class="btn btn-ghost view-btn"
                :class="{ active: libraryStore.viewMode === 'grid' }"
                @click="libraryStore.viewMode = 'grid'"
                title="网格视图"
              >⊞</button>
              <button
                class="btn btn-ghost view-btn"
                :class="{ active: libraryStore.viewMode === 'list' }"
                @click="libraryStore.viewMode = 'list'"
                title="列表视图"
              >☰</button>
            </div>
            <button class="btn btn-primary" @click="libraryStore.search()">
              搜索
            </button>
          </div>
        </div>

        <!-- 统计信息 -->
        <div class="library-stats">
          <span class="badge badge-info">{{ labels.library.totalAssets }}：{{ libraryStore.stats.total_assets }}</span>
          <span v-if="libraryStore.stats.video_assets" class="badge badge-info">视频 {{ libraryStore.stats.video_assets }}</span>
          <span v-if="libraryStore.stats.image_assets" class="badge badge-info">图片 {{ libraryStore.stats.image_assets }}</span>
        </div>

        <!-- 导入面板 -->
        <IngestPanel />

        <!-- 素材列表 -->
        <div v-if="libraryStore.loading" class="empty-state">
          <div class="ai-spinner">{{ labels.common.loading }}</div>
        </div>
        <div v-else-if="libraryStore.results.length === 0" class="empty-state">
          <div class="empty-state-icon">📁</div>
          <div class="empty-state-title">{{ labels.library.empty }}</div>
          <div class="empty-state-text">{{ labels.library.emptyHint }}</div>
        </div>

        <!-- 网格视图 -->
        <div v-else-if="libraryStore.viewMode === 'grid'" class="library-grid">
          <LibraryAssetCard
            v-for="asset in libraryStore.results"
            :key="asset.uid"
            :asset="asset"
          />
        </div>

        <!-- 列表视图 -->
        <div v-else class="library-list">
          <div class="list-header">
            <span class="list-h-thumb"></span>
            <span class="list-h-name">文件名</span>
            <span class="list-h-kind">类型</span>
            <span class="list-h-meta">时长</span>
            <span class="list-h-meta">分辨率</span>
            <span class="list-h-tags">标签</span>
            <span class="list-h-quality">质量</span>
          </div>
          <LibraryAssetRow
            v-for="asset in libraryStore.results"
            :key="asset.uid"
            :asset="asset"
          />
        </div>

        <!-- 加载更多 -->
        <div v-if="libraryStore.hasMore" style="text-align: center; margin-top: 16px">
          <button class="btn btn-ghost" @click="libraryStore.loadMore()">加载更多</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useLibraryStore } from '../stores/library.js'
import labels from '../i18n/labels.js'
import AppNav from '../components/layout/AppNav.vue'
import IngestPanel from '../components/library/IngestPanel.vue'
import LibraryAssetCard from '../components/library/LibraryAssetCard.vue'
import LibraryAssetRow from '../components/library/LibraryAssetRow.vue'

const appStore = useAppStore()
const libraryStore = useLibraryStore()

onMounted(async () => {
  await libraryStore.loadStats()
  await libraryStore.search()
})
</script>

<style scoped>
.library-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.search-box {
  flex: 1;
}

.toolbar-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.view-toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.view-btn {
  padding: 4px 8px;
  font-size: 14px;
  border-radius: 0;
  border: none;
  min-width: 32px;
}

.view-btn.active {
  background: var(--accent);
  color: #fff;
}

.library-stats {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.library-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.library-list {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.list-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--surface2);
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}

.list-h-thumb { width: 48px; flex-shrink: 0; }
.list-h-name { flex: 1; }
.list-h-kind { width: 48px; flex-shrink: 0; }
.list-h-meta { width: 60px; text-align: center; flex-shrink: 0; }
.list-h-tags { width: 200px; flex-shrink: 0; }
.list-h-quality { width: 30px; flex-shrink: 0; }
</style>
