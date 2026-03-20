<template>
  <Teleport to="body">
    <div v-if="visible" class="detail-overlay" @click.self="$emit('close')">
      <div class="detail-panel">
        <div class="detail-header">
          <h3>{{ asset.filename || '未知文件' }}</h3>
          <button class="btn btn-ghost btn-close" @click="$emit('close')">✕</button>
        </div>

        <!-- 视频/图片预览 -->
        <div class="detail-preview">
          <video
            v-if="asset.asset_kind === 'video' && asset.thumbnail_url"
            :src="asset.thumbnail_url.replace('/thumb/', '/video/')"
            :poster="asset.thumbnail_url"
            controls
            class="preview-media"
          />
          <img
            v-else-if="asset.thumbnail_url"
            :src="asset.thumbnail_url"
            :alt="asset.filename"
            class="preview-media"
          />
          <div v-else class="preview-placeholder">
            <span class="placeholder-icon">{{ asset.asset_kind === 'video' ? '🎬' : '🖼️' }}</span>
            <span>无预览</span>
          </div>
        </div>

        <!-- 元数据 -->
        <div class="detail-meta">
          <div class="meta-grid">
            <div class="meta-item">
              <span class="meta-label">类型</span>
              <span class="meta-value">{{ asset.asset_kind === 'video' ? '视频' : '图片' }}</span>
            </div>
            <div v-if="asset.duration" class="meta-item">
              <span class="meta-label">时长</span>
              <span class="meta-value">{{ formatDuration(asset.duration) }}</span>
            </div>
            <div v-if="asset.resolution" class="meta-item">
              <span class="meta-label">分辨率</span>
              <span class="meta-value">{{ asset.resolution }}</span>
            </div>
            <div v-if="asset.quality_score" class="meta-item">
              <span class="meta-label">质量</span>
              <span class="meta-value">
                <span class="quality-badge" :class="qualityClass(asset.quality_score)">
                  {{ qualityLabel(asset.quality_score) }}
                </span>
                <span class="quality-num">{{ (asset.quality_score * 100).toFixed(0) }}分</span>
              </span>
            </div>
            <div v-if="asset.gps_latitude && asset.gps_longitude" class="meta-item">
              <span class="meta-label">位置</span>
              <span class="meta-value">📍 {{ Number(asset.gps_latitude).toFixed(4) }}, {{ Number(asset.gps_longitude).toFixed(4) }}</span>
            </div>
            <div v-if="asset.file_size" class="meta-item">
              <span class="meta-label">大小</span>
              <span class="meta-value">{{ formatSize(asset.file_size) }}</span>
            </div>
          </div>
        </div>

        <!-- 标签 -->
        <div v-if="allTags.length > 0" class="detail-tags">
          <div class="meta-label" style="margin-bottom: 8px">语义标签</div>
          <div class="tags-wrap">
            <span v-for="tag in allTags" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>

        <!-- 转录文字 -->
        <div v-if="asset.transcript" class="detail-transcript">
          <div class="meta-label" style="margin-bottom: 8px">语音转录</div>
          <div class="transcript-text">{{ asset.transcript }}</div>
        </div>

        <!-- 操作 -->
        <div class="detail-actions">
          <button class="btn btn-primary btn-sm" @click="$emit('show-evidence', { assetId: asset.uid, filename: asset.filename })">
            查看解释
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, watch, onBeforeUnmount } from 'vue'
import { translateTag } from '../../composables/useSemanticTranslation.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  asset: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['close', 'show-evidence'])

// Esc 键关闭面板
function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

watch(() => props.visible, (v) => {
  if (v) {
    document.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('keydown', onKeydown)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})

function qualityLabel(score) {
  const n = Number(score)
  if (n >= 0.9) return '优秀'
  if (n >= 0.7) return '良好'
  if (n >= 0.5) return '一般'
  return '较差'
}

function qualityClass(score) {
  const n = Number(score)
  if (n >= 0.9) return 'q-excellent'
  if (n >= 0.7) return 'q-good'
  return 'q-fair'
}

function formatDuration(seconds) {
  const s = Number(seconds) || 0
  if (s < 60) return `${Math.round(s)}秒`
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${m}分${sec}秒`
}

function formatSize(bytes) {
  const b = Number(bytes) || 0
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

const allTags = computed(() => {
  const semantic = props.asset.semantic
  if (!semantic || typeof semantic !== 'object') {
    return (props.asset.semantic_keywords || []).map(t => translateTag(t))
  }
  const st = semantic.structured_tags
  if (!st || typeof st !== 'object') return []
  const tags = []
  for (const arr of Object.values(st)) {
    if (Array.isArray(arr)) {
      for (const t of arr) tags.push(translateTag(t))
    }
  }
  return [...new Set(tags)].slice(0, 40)
})
</script>

<style scoped>
.detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
  animation: fadeIn 0.15s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.detail-panel {
  width: 420px;
  max-width: 90vw;
  height: 100vh;
  background: var(--surface, #1a1a2e);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  animation: slideIn 0.2s ease;
}

@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #333);
}

.detail-header h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 12px;
}

.btn-close {
  font-size: 18px;
  min-width: 36px;
  height: 36px;
  padding: 0;
  flex-shrink: 0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 1;
}

.btn-close:hover {
  background: rgba(255, 255, 255, 0.1);
}

.detail-preview {
  background: #000;
  aspect-ratio: 16 / 9;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-media {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--muted, #888);
}

.preview-placeholder .placeholder-icon {
  font-size: 48px;
}

.detail-meta {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #333);
}

.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.meta-label {
  font-size: 11px;
  color: var(--muted, #888);
  font-weight: 600;
  text-transform: uppercase;
}

.meta-value {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.quality-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
}

.q-excellent { background: rgba(76, 175, 80, 0.15); color: #4caf50; }
.q-good { background: rgba(90, 141, 238, 0.15); color: var(--accent, #5a8dee); }
.q-fair { background: rgba(255, 152, 0, 0.15); color: #ff9800; }

.quality-num {
  font-size: 11px;
  color: var(--muted, #888);
}

.detail-tags {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #333);
}

.tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-transcript {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #333);
}

.transcript-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary, #ccc);
  max-height: 120px;
  overflow-y: auto;
}

.detail-actions {
  padding: 16px 20px;
}
</style>
