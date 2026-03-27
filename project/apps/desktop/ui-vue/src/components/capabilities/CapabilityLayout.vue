<template>
  <div class="capability-layout">
    <!-- 左侧导航 -->
    <aside class="capability-nav">
      <div class="cap-nav-hint">独立使用单个工具，不走工作流。需要按步骤创作请前往「创作」。</div>
      <div v-for="group in allGroups" :key="group.key" class="cap-group">
        <div class="cap-group-title">{{ group.title }}</div>
        <div
          v-for="item in group.items"
          :key="item.tab"
          class="cap-item"
          :class="{ active: currentTab === item.tab }"
          @click="selectTab(item.tab)"
        >
          <span class="cap-item-label">
            {{ item.label }}
            <span v-if="capStore.statusText(item.tab)"
                  class="cap-status-badge"
                  :class="capStore.statusClass(item.tab)">
              {{ capStore.statusText(item.tab) }}
            </span>
          </span>
          <span class="cap-item-hint text-muted">{{ item.hint }}</span>
        </div>
      </div>
    </aside>

    <!-- 右侧面板 -->
    <div class="capability-content">
      <!-- 消息提示 -->
      <div v-if="capStore.message" class="badge" :class="`badge-${capStore.messageType}`" style="margin-bottom: 12px">
        {{ capStore.message }}
      </div>

      <!-- 面板内容 -->
      <div class="cap-panel">
        <component :is="panelComponent" :key="currentTab" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import CapabilityPlaceholder from './CapabilityPlaceholder.vue'
import TopicLibrary from './TopicLibrary.vue'
import TopicCopy from './TopicCopy.vue'
import TextRoughCut from './TextRoughCut.vue'
import ShortClip from './ShortClip.vue'
import Refinement from './Refinement.vue'
import AudioVoice from './AudioVoice.vue'
import SubtitleCalibration from './SubtitleCalibration.vue'
import ImageSemantic from './ImageSemantic.vue'
import ArticleExpand from './ArticleExpand.vue'
import PublishPrep from './PublishPrep.vue'
import SocialExport from './SocialExport.vue'
import ContentPublish from './ContentPublish.vue'
import AgentTemplates from './AgentTemplates.vue'
import AgentObservability from './AgentObservability.vue'

const panelMap = {
  topic_library: TopicLibrary,
  topic_copy: TopicCopy,
  text_rough: TextRoughCut,
  short_clip: ShortClip,
  refinement: Refinement,
  audio_voice: AudioVoice,
  subtitle_calibration: SubtitleCalibration,
  image_semantic: ImageSemantic,
  article_expand: ArticleExpand,
  publish_prep: PublishPrep,
  social_export: SocialExport,
  content_publish: ContentPublish,
  agent_templates: AgentTemplates,
  agent_observability: AgentObservability,
}

const route = useRoute()
const router = useRouter()
const capStore = useCapabilitiesStore()

const allGroups = computed(() => [...capStore.groups, ...capStore.systemGroups])

const currentTab = computed(() => {
  return route.params.tab || capStore.activeTab || 'topic_library'
})

// 保持 store.activeTab 与路由参数同步
watch(() => route.params.tab, (tab) => {
  if (tab) capStore.activeTab = tab
}, { immediate: true })

const panelComponent = computed(() => {
  return panelMap[currentTab.value] || CapabilityPlaceholder
})

onMounted(() => {
  capStore.loadStatuses()
})

function selectTab(tab) {
  const status = capStore.statuses[tab]
  if (status === 'planned') {
    capStore.setMessage('该模块正在开发中，敬请期待', 'info')
    return
  }
  const hint = capStore.executionHint(tab)
  if (hint) {
    capStore.setMessage(hint, 'warn')
    return
  }
  capStore.activeTab = tab
  router.push(`/tools/${tab}`)
}
</script>

<style scoped>
.capability-layout {
  display: flex;
  height: 100%;
}

.capability-nav {
  width: 200px;
  border-right: 1px solid var(--border);
  padding: 16px 0;
  overflow-y: auto;
  flex-shrink: 0;
}

.cap-group {
  margin-bottom: 16px;
}

.cap-nav-hint {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
  padding: 8px 16px 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.cap-group-title {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--muted);
  letter-spacing: 0.08em;
  padding: 0 16px;
  margin-bottom: 4px;
}

.cap-item {
  display: flex;
  flex-direction: column;
  padding: 6px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.cap-item:hover {
  background: var(--surface2);
}

.cap-item.active {
  background: rgba(90, 141, 238, 0.1);
  border-left: 3px solid var(--accent);
}

.cap-item-label {
  font-size: 13px;
  font-weight: 500;
}

.cap-item-hint {
  font-size: 11px;
}

.cap-status-badge {
  display: inline-block;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 4px;
  vertical-align: middle;
  font-weight: 400;
}

.cap-status-badge.badge-success {
  background: rgba(52, 199, 89, 0.15);
  color: #34c759;
}

.cap-status-badge.badge-info {
  background: rgba(90, 141, 238, 0.15);
  color: #5a8dee;
}

.cap-status-badge.badge-muted {
  background: var(--surface2, rgba(128, 128, 128, 0.1));
  color: var(--muted, #888);
}

.cap-status-badge.badge-warn {
  background: rgba(255, 159, 10, 0.15);
  color: #ff9f0a;
}

.capability-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
</style>
