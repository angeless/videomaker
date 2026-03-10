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
          <SearchAutocomplete
            v-model="libraryStore.query"
            :placeholder="labels.library.search"
            @search="libraryStore.search()"
            @select-tag="onSelectTag"
          />
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
          <span v-if="libraryStore.totalMatches > 0 && libraryStore.query" class="badge badge-accent">
            命中 {{ libraryStore.totalMatches }}
          </span>
        </div>

        <!-- 面板分组切换器 -->
        <div class="panel-group-switcher">
          <button
            class="btn btn-sm"
            :class="panelGroup === 'browse' ? 'btn-primary' : 'btn-ghost'"
            @click="panelGroup = 'browse'"
          >导入与浏览</button>
          <button
            class="btn btn-sm"
            :class="panelGroup === 'health' ? 'btn-primary' : 'btn-ghost'"
            @click="panelGroup = 'health'"
          >维护</button>
          <button
            class="btn btn-sm"
            :class="panelGroup === 'relink' ? 'btn-primary' : 'btn-ghost'"
            @click="panelGroup = 'relink'"
          >工程修复</button>
        </div>
        <div v-if="isLibraryEmpty" class="panel-group-hint">
          首次使用：先导入素材，再搜索或浏览。需要修复剪辑工程请切换到「工程修复」。
        </div>

        <!-- 组: 导入与浏览 (默认) -->
        <template v-if="panelGroup === 'browse'">
          <IngestPanel ref="ingestRef" />
          <TagBrowser @search-tag="onBrowseTag" />
          <SearchAnalyticsPanel @search-query="onBrowseTag" />
          <CustomTagPanel @search-tag="onBrowseTag" />
        </template>

        <!-- 组: 维护 -->
        <template v-if="panelGroup === 'health'">
          <LibraryHealthPanel />
          <DuplicateGroupsPanel />
          <LocationHealthPanel2 />
        </template>

        <!-- 组: 工程修复 -->
        <template v-if="panelGroup === 'relink'">
          <RelinkReportPanel />
          <ProjectRelinkPanel @search-library="onSearchFromRelink" />
        </template>

        <!-- 素材列表 -->
        <div v-if="libraryStore.loading" class="empty-state">
          <div class="ai-spinner">{{ labels.common.loading }}</div>
        </div>
        <div v-else-if="libraryStore.results.length === 0" class="empty-state">
          <div class="empty-state-icon">📁</div>
          <div class="empty-state-title">{{ labels.library.empty }}</div>
          <div class="empty-state-text">{{ labels.library.emptyHint }}</div>
          <div v-if="isLibraryEmpty" class="empty-state-actions">
            <button class="btn btn-primary" @click="scrollToIngest">导入素材</button>
            <router-link to="/settings" class="btn btn-ghost">配置 AI</router-link>
          </div>
        </div>

        <!-- 网格视图 -->
        <div v-else-if="libraryStore.viewMode === 'grid'" class="library-grid">
          <LibraryAssetCard
            v-for="asset in libraryStore.results"
            :key="asset.uid"
            :asset="asset"
            @show-evidence="openEvidence"
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

  <!-- P4-3: 证据链面板 -->
  <EvidencePanel
    :visible="evidenceVisible"
    :asset-id="evidenceAssetId"
    :asset-filename="evidenceFilename"
    @close="evidenceVisible = false"
    @feedback-done="onFeedbackDone"
  />
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useLibraryStore } from '../stores/library.js'
import labels from '../i18n/labels.js'
import AppNav from '../components/layout/AppNav.vue'
import IngestPanel from '../components/library/IngestPanel.vue'
import LibraryAssetCard from '../components/library/LibraryAssetCard.vue'
import LibraryAssetRow from '../components/library/LibraryAssetRow.vue'
import SearchAutocomplete from '../components/library/SearchAutocomplete.vue'
import EvidencePanel from '../components/library/EvidencePanel.vue'
import TagBrowser from '../components/library/TagBrowser.vue'
import CustomTagPanel from '../components/library/CustomTagPanel.vue'
import SearchAnalyticsPanel from '../components/library/SearchAnalyticsPanel.vue'
import LibraryHealthPanel from '../components/library/LibraryHealthPanel.vue'
import DuplicateGroupsPanel from '../components/library/DuplicateGroupsPanel.vue'
import LocationHealthPanel2 from '../components/library/LocationHealthPanel2.vue'
import RelinkReportPanel from '../components/library/RelinkReportPanel.vue'
import ProjectRelinkPanel from '../components/library/ProjectRelinkPanel.vue'

const appStore = useAppStore()
const libraryStore = useLibraryStore()

// Panel group switcher — local ref, resets to 'browse' on each visit
const panelGroup = ref('browse')

// IngestPanel ref for programmatic expand + scroll
const ingestRef = ref(null)

// Evidence panel state
const evidenceVisible = ref(false)
const evidenceAssetId = ref('')
const evidenceFilename = ref('')

// Empty library detection
const isLibraryEmpty = computed(() => libraryStore.stats.total_assets === 0)

function openEvidence({ assetId, filename }) {
  evidenceAssetId.value = assetId
  evidenceFilename.value = filename
  evidenceVisible.value = true
}

function onSelectTag(item) {
  // Tag selected from autocomplete — search triggers via @search event
}

function onBrowseTag(tagName) {
  libraryStore.query = tagName
  libraryStore.search()
}

// D-1: Jump from relink missing item → library search (one-way, hard rule #6)
function onSearchFromRelink(assetName) {
  const stem = assetName.replace(/\.[^.]+$/, '')
  libraryStore.query = stem
  libraryStore.search()
}

function onFeedbackDone(detail) {
  // After feedback (confirm/reject/add), refresh search results to reflect score changes
  libraryStore.search()
}

function scrollToIngest() {
  panelGroup.value = 'browse'
  nextTick(() => {
    if (ingestRef.value) {
      ingestRef.value.expand()
      ingestRef.value.scrollIntoView({ behavior: 'smooth' })
    }
  })
}

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

.badge-accent {
  background: rgba(90, 141, 238, 0.15);
  color: var(--accent);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
}

.panel-group-switcher {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
}

.panel-group-hint {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 12px;
  line-height: 1.4;
}

.empty-state-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  justify-content: center;
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
