<!--
  MissingKeyBanner.vue — v0.19 Wave 1 Task M2 + M9

  Surfaces LLM-tagging configuration status to the user. When neither
  OpenAI nor Anthropic key is configured, library tagging silently
  falls back to colour-rule heuristics (Issue A from 2026-05-08 user
  report). Banner makes that degradation visible + provides a one-click
  path to Settings AI section (M9).

  Reusable across views (M2 Library + future surfaces). Per
  plan-audit-A-H4: NEW component, NOT a copy of DiagnosticsPanel's
  `dp-notice` style.

  Behavior:
  - Polls `/api/library/llm-status` on mount + when `refresh-trigger`
    prop changes (e.g. after Settings save).
  - Hidden when `enabled === true` OR session-dismissed.
  - Session-dismiss only — `sessionStorage` clears on app restart.
  - Reappears on app restart so users keep seeing the honest signal
    until they configure or explicitly disable via env var.
-->

<template>
  <transition name="banner-fade">
    <div
      v-if="visible"
      class="missing-key-banner"
      role="status"
      aria-live="polite"
    >
      <span class="mkb-icon" aria-hidden="true">⚠️</span>
      <span class="mkb-text">
        {{ statusMessage }}
        <span class="mkb-hint">{{ hintText }}</span>
      </span>
      <div class="mkb-actions">
        <button
          class="mkb-btn mkb-btn-primary"
          @click="goToSettings"
        >
          立即配置
        </button>
        <button
          class="mkb-btn-close"
          aria-label="关闭横幅（本次会话）"
          title="本次会话内不再显示（重启后会再次提醒）"
          @click="dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useApiStore } from '../../stores/api.js'

// session-storage key — banner stays dismissed for this session only
const DISMISS_KEY = 'mkb_dismissed_v1'

const props = defineProps({
  // bumping this prop re-fetches status (e.g. after Settings save)
  refreshTrigger: { type: Number, default: 0 },
  // anchor to scroll to in Settings page (M9)
  settingsAnchor: { type: String, default: 'ai-config' },
})

const router = useRouter()
const api = useApiStore()

const status = ref(null)        // null = loading; object = fetched
const fetchError = ref(false)   // true if endpoint unreachable
const dismissed = ref(false)

onMounted(() => {
  dismissed.value = sessionStorage.getItem(DISMISS_KEY) === '1'
  fetchStatus()
})

watch(() => props.refreshTrigger, () => {
  // user may have configured a key — clear dismiss to re-evaluate
  dismissed.value = false
  sessionStorage.removeItem(DISMISS_KEY)
  fetchStatus()
})

async function fetchStatus() {
  try {
    const data = await api.api('/api/library/llm-status', { method: 'GET' })
    status.value = data
    fetchError.value = false
  } catch (e) {
    // Endpoint failures should NOT show a fake banner — silently hide.
    // If LLM is genuinely missing, the next successful poll will reveal it.
    fetchError.value = true
    status.value = null
  }
}

const visible = computed(() => {
  if (dismissed.value) return false
  if (fetchError.value) return false
  if (!status.value) return false
  return status.value.enabled === false
})

const statusMessage = computed(() => {
  if (!status.value) return ''
  return status.value.message || 'AI 标签未启用'
})

const hintText = computed(() => {
  const reason = status.value?.reason
  if (reason === 'disabled') {
    return '（已通过环境变量显式禁用，不影响指纹去重）'
  }
  if (reason === 'missing_api_key') {
    return '当前用颜色规则推断标签，可能不准。配置 OpenAI 或 Anthropic Key 后启用真正的 AI 语义标签。'
  }
  return ''
})

function dismiss() {
  dismissed.value = true
  sessionStorage.setItem(DISMISS_KEY, '1')
}

function goToSettings() {
  router.push({ path: '/settings', hash: `#${props.settingsAnchor}` })
}
</script>

<style scoped>
.missing-key-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin: 12px 0;
  background: linear-gradient(
    90deg,
    rgba(245, 158, 11, 0.18),
    rgba(245, 158, 11, 0.08)
  );
  border: 1px solid rgba(245, 158, 11, 0.4);
  border-radius: 8px;
  color: var(--text-primary, #f4f4f4);
  font-size: 13px;
  line-height: 1.5;
}

.mkb-icon {
  flex-shrink: 0;
  font-size: 18px;
}

.mkb-text {
  flex: 1;
}

.mkb-hint {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted, #a8a8a8);
}

.mkb-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.mkb-btn {
  background: rgba(245, 158, 11, 0.9);
  color: #1a1a1a;
  border: none;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.mkb-btn:hover { background: rgba(245, 158, 11, 1); }

.mkb-btn-primary { white-space: nowrap; }

.mkb-btn-close {
  background: transparent;
  border: none;
  color: var(--text-muted, #a8a8a8);
  font-size: 14px;
  cursor: pointer;
  padding: 4px 6px;
  opacity: 0.7;
  transition: opacity 0.15s;
}
.mkb-btn-close:hover { opacity: 1; }

.banner-fade-enter-active,
.banner-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.banner-fade-enter-from,
.banner-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
