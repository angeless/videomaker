<template>
  <div>
    <h3>视频精剪</h3>

    <div class="cap-section">
      <div class="cap-subtitle">精剪策略</div>
      <div class="form-row"><label>风格</label>
        <select v-model="refineInput.style" class="form-input">
          <option value="travel_story">旅行故事</option><option value="cinematic">电影感</option><option value="clean_vlog">干净 Vlog</option>
        </select>
      </div>
      <div class="form-row"><label>编辑器</label>
        <select v-model="refineInput.editor" class="form-input">
          <option value="internal_ffmpeg">内置 FFmpeg</option><option value="davinci">DaVinci Resolve</option>
          <option value="finalcut">Final Cut Pro</option><option value="premiere">Premiere Pro</option><option value="jianying">剪映</option>
        </select>
      </div>
      <div class="form-row"><label>品质</label>
        <select v-model="refineInput.quality" class="form-input">
          <option value="draft">草稿</option><option value="high">高品质</option><option value="premium">最佳</option>
        </select>
      </div>
      <button class="btn btn-sm" @click="buildPlan" :disabled="!appStore.projectDir || loadingPlan">{{ loadingPlan ? '生成中…' : '生成策略' }}</button>
    </div>

    <div v-if="connectors.length" class="cap-section">
      <div class="cap-subtitle">NLE 连接器状态</div>
      <div v-for="c in connectors" :key="c.editor" class="connector-row">
        <span class="badge" :class="c.available ? 'badge-success' : 'badge-warning'">{{ c.editor }}</span>
        <span class="text-muted" style="margin-left:8px">{{ c.path || '未检测到' }}</span>
      </div>
      <p v-if="connectors.every(c => !c.available)" class="connector-hint">
        未检测到外部编辑器。仍可使用内置 FFmpeg 精剪，或安装 DaVinci Resolve / Final Cut Pro / 剪映后重新进入此页面。
      </p>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">NLE 交接</div>
      <div class="form-row"><label>编辑器</label>
        <select v-model="handoff.editor" class="form-input">
          <option value="finalcut">Final Cut Pro</option><option value="davinci">DaVinci Resolve</option>
          <option value="premiere">Premiere Pro</option><option value="jianying">剪映</option>
        </select>
      </div>
      <div class="form-row"><label>时间线标题</label><input v-model="handoff.title" class="form-input" /></div>
      <div class="form-row"><label>帧率</label><input v-model.number="handoff.fps" type="number" class="form-input" /></div>
      <div class="form-row"><label>自动启动</label><input type="checkbox" v-model="handoff.launch" /></div>
      <div class="btn-row">
        <button class="btn btn-sm" @click="buildHandoff" :disabled="!appStore.projectDir || loadingHandoff">{{ loadingHandoff ? '生成中…' : '生成交接包' }}</button>
        <button class="btn btn-primary btn-sm" @click="execute" :disabled="!appStore.projectDir || loadingExecute">{{ loadingExecute ? '执行中…' : '执行并启动' }}</button>
      </div>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">导回成片</div>
      <div class="form-row"><label>来源路径</label><input v-model="handoff.master_source" class="form-input" placeholder="留空自动扫描" /></div>
      <div class="form-row"><label>输出文件名</label><input v-model="handoff.output_name" class="form-input" /></div>
      <div class="form-row"><label>复制模式</label>
        <select v-model="handoff.copy_mode" class="form-input"><option value="copy">复制</option><option value="move">移动</option></select>
      </div>
      <button class="btn btn-sm" @click="collect" :disabled="!appStore.projectDir || loadingCollect">{{ loadingCollect ? '导回中…' : '导回成片' }}</button>
    </div>

    <div v-if="refinePlan || handoffResult" class="cap-section">
      <div class="cap-subtitle">结果</div>
      <pre v-if="refinePlan" class="result-pre">{{ JSON.stringify(refinePlan, null, 2) }}</pre>
      <pre v-if="handoffResult" class="result-pre">{{ JSON.stringify(handoffResult, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()

const refineInput = reactive({ style: 'travel_story', editor: 'internal_ffmpeg', quality: 'high' })
const handoff = reactive({
  editor: 'finalcut', title: 'VideoEditer Timeline', fps: 30,
  launch: true, app_name: '', master_source: '', output_name: 'final.mp4', copy_mode: 'copy',
})
const connectors = ref([])
const refinePlan = ref(null)
const handoffResult = ref(null)
const loadingPlan = ref(false)
const loadingHandoff = ref(false)
const loadingExecute = ref(false)
const loadingCollect = ref(false)

async function loadConnectors() {
  const data = await apiStore.api('GET', '/api/capabilities/refinement/connectors')
  if (!data.error) connectors.value = Array.isArray(data.connectors) ? data.connectors : []
}

async function buildPlan() {
  if (loadingPlan.value) return
  loadingPlan.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/refinement/plan', {
      style: refineInput.style, editor: refineInput.editor, quality: refineInput.quality,
    })
    if (data.error) { capStore.setMessage(`精剪策略生成失败：${data.error}`, 'error'); return }
    refinePlan.value = data.plan || null
    capStore.setMessage('已生成精剪策略', 'success')
  } finally {
    loadingPlan.value = false
  }
}

async function buildHandoff() {
  if (!appStore.projectDir || loadingHandoff.value) return
  loadingHandoff.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/refinement/handoff', {
      editor: handoff.editor, title: handoff.title, fps: handoff.fps,
    })
    if (data.error) { capStore.setMessage(`NLE 交接包生成失败：${data.error}`, 'error'); return }
    handoffResult.value = data.handoff || null
    capStore.setMessage('已生成 NLE 交接包', 'success')
  } finally {
    loadingHandoff.value = false
  }
}

async function execute() {
  if (!appStore.projectDir || loadingExecute.value) return
  loadingExecute.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/refinement/execute', {
      editor: handoff.editor, title: handoff.title, fps: handoff.fps,
      launch: handoff.launch, app_name: handoff.app_name,
    })
    if (data.error) { capStore.setMessage(`NLE 执行失败：${data.error}`, 'error'); return }
    handoffResult.value = data.handoff || null
    capStore.setMessage(handoff.launch ? '已生成交接包并启动外部编辑器' : '已生成交接包', 'success')
  } finally {
    loadingExecute.value = false
  }
}

async function collect() {
  if (!appStore.projectDir || loadingCollect.value) return
  loadingCollect.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/refinement/collect_master', {
      editor: handoff.editor, source_video: handoff.master_source,
      output_name: handoff.output_name, copy_mode: handoff.copy_mode,
    })
    if (data.error) { capStore.setMessage(`导回成片失败：${data.error}`, 'error'); return }
    handoffResult.value = data.collect || data.record || null
    capStore.setMessage(`已导回外部精剪成片`, 'success')
  } finally {
    loadingCollect.value = false
  }
}

onMounted(() => { loadConnectors() })
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.form-row label { width: 90px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 8px; margin-top: 8px; }
.connector-row { display: flex; align-items: center; margin-bottom: 4px; }
.connector-hint { font-size: 12px; color: var(--muted); margin-top: 8px; line-height: 1.5; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
</style>
