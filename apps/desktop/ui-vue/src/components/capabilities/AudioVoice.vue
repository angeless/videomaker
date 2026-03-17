<template>
  <div>
    <h3>配乐配音</h3>

    <div class="cap-section">
      <div class="cap-subtitle">配音设置</div>
      <div class="form-row"><label>叙事风格</label>
        <select v-model="input.mood" class="form-input">
          <option value="travel_story">旅行叙事</option>
          <option value="daily_vlog">日常 Vlog</option>
          <option value="food_review">美食探店</option>
          <option value="tutorial">教程讲解</option>
          <option value="cinematic">电影感旁白</option>
          <option value="energetic">活力快节奏</option>
          <option value="calm">舒缓治愈</option>
        </select>
      </div>
      <div class="form-row"><label>语音合成</label>
        <select v-model="input.provider" class="form-input">
          <option value="elevenlabs">ElevenLabs 语音合成</option>
          <option value="azure">Azure 语音服务</option>
          <option value="edge_tts">Edge TTS（免费）</option>
          <option value="local">本地 TTS</option>
        </select>
      </div>
      <div class="form-row"><label>音色 ID</label><input v-model="input.voice_id" class="form-input" placeholder="留空使用默认音色" /></div>
      <div class="form-row"><label>模型</label>
        <select v-model="input.model_id" class="form-input">
          <option value="eleven_multilingual_v2">多语言 V2（推荐）</option>
          <option value="eleven_monolingual_v1">英文专用 V1</option>
          <option value="eleven_turbo_v2">快速生成 V2</option>
        </select>
      </div>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">背景音乐</div>
      <div class="form-row"><label>音乐来源</label>
        <select v-model="input.bgm_provider" class="form-input">
          <option value="local_library">本地音乐库</option>
          <option value="api">在线曲库</option>
        </select>
      </div>
      <div class="form-row"><label>音乐目录</label><input v-model="input.bgm_library_dir" class="form-input" placeholder="留空使用默认目录" /></div>
      <div class="form-row"><label>自动选曲</label><input type="checkbox" v-model="input.auto_pick_bgm" /></div>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">混音参数</div>
      <div class="form-row"><label>原声音量</label><input v-model.number="input.origin_volume" type="number" step="0.05" class="form-input" /></div>
      <div class="form-row"><label>旁白音量</label><input v-model.number="input.narration_volume" type="number" step="0.05" class="form-input" /></div>
      <div class="form-row"><label>BGM 音量</label><input v-model.number="input.bgm_volume" type="number" step="0.05" class="form-input" /></div>
      <div class="form-row"><label>替换成片</label><input type="checkbox" v-model="input.replace_master" /></div>
    </div>

    <div class="btn-row btn-row-sticky">
      <button class="btn btn-sm" :class="{ 'btn-done': donePlan }" @click="plan" :disabled="!appStore.projectDir || loadingPlan">{{ loadingPlan ? '规划中…' : donePlan ? '✓ 规划' : '规划' }}</button>
      <button class="btn btn-sm" :class="{ 'btn-done': doneSynthesize }" @click="synthesize" :disabled="!appStore.projectDir || loadingSynthesize">{{ loadingSynthesize ? '合成中…' : doneSynthesize ? '✓ 合成配音' : '合成配音' }}</button>
      <button class="btn btn-sm" :class="{ 'btn-done': doneTimeline }" @click="buildTimeline" :disabled="!appStore.projectDir || loadingTimeline">{{ loadingTimeline ? '生成中…' : doneTimeline ? '✓ 生成旁白轨' : '生成旁白轨' }}</button>
      <button class="btn btn-sm" :class="{ 'btn-done': doneBgm }" @click="pickBgm" :disabled="!appStore.projectDir || loadingBgm">{{ loadingBgm ? '选曲中…' : doneBgm ? '✓ 选配乐' : '选配乐' }}</button>
      <button class="btn btn-sm" :class="{ 'btn-done': doneMix }" @click="mix" :disabled="!appStore.projectDir || loadingMix">{{ loadingMix ? '混音中…' : doneMix ? '✓ 混音' : '混音' }}</button>
      <button class="btn btn-primary btn-sm" :class="{ 'btn-done': donePipeline }" @click="runPipeline" :disabled="!appStore.projectDir || running">
        {{ running ? '执行中…' : donePipeline ? '✓ 一键全流程' : '一键全流程' }}
      </button>
    </div>

    <div v-if="running" class="cap-section" style="margin-top:12px">
      <div class="progress"><div class="progress-fill" :style="{ width: progress + '%' }"></div></div>
    </div>

    <div v-if="result" class="cap-section" style="margin-top:12px">
      <div class="cap-subtitle">结果</div>
      <pre class="result-pre">{{ JSON.stringify(result, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useApiStore } from '../../stores/api.js'
import { useCapabilitiesStore } from '../../stores/capabilities.js'
import { useAppStore } from '../../stores/app.js'
import { useJobPoller } from '../../composables/useJobPoller.js'

const apiStore = useApiStore()
const capStore = useCapabilitiesStore()
const appStore = useAppStore()
const { waitForJob } = useJobPoller()

const input = reactive({
  mood: 'travel_story', provider: 'elevenlabs', voice_id: '', api_key: '',
  model_id: 'eleven_multilingual_v2', output_dir: '', dry_run: false,
  bgm_provider: 'local_library', bgm_library_dir: '', bgm_endpoint: '', bgm_api_key: '',
  bgm_download: false, bgm_cache_enabled: true, bgm_force_refresh: false, bgm_audio: '',
  auto_pick_bgm: true, master_input: '', timeline_output: '', mix_output: '',
  replace_master: true, origin_volume: 0.8, narration_volume: 1.0, bgm_volume: 0.25,
  enable_ducking: true, ducking_threshold: 0.03, ducking_ratio: 8.0,
  ducking_attack_ms: 15, ducking_release_ms: 250, bgm_loop: false, bgm_fade_out_s: 0,
})
const result = ref(null)
const running = ref(false)
const progress = ref(0)
const loadingPlan = ref(false)
const loadingSynthesize = ref(false)
const loadingTimeline = ref(false)
const loadingBgm = ref(false)
const loadingMix = ref(false)
const donePlan = ref(false)
const doneSynthesize = ref(false)
const doneTimeline = ref(false)
const doneBgm = ref(false)
const doneMix = ref(false)
const donePipeline = ref(false)

function basePayload() {
  return {
    mood: input.mood, provider: input.provider, voice_id: input.voice_id,
    api_key: input.api_key, model_id: input.model_id, output_dir: input.output_dir,
    dry_run: input.dry_run,
  }
}

async function plan() {
  if (loadingPlan.value) return
  loadingPlan.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/audio_voice/plan', { mood: input.mood })
    if (data.error) { capStore.setMessage(`配乐配音规划失败：${data.error}`, 'error'); return }
    result.value = data.plan || null
    donePlan.value = true
    capStore.setMessage('已生成配乐和配音规划', 'success')
  } finally {
    loadingPlan.value = false
  }
}

async function synthesize() {
  if (loadingSynthesize.value) return
  loadingSynthesize.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/audio_voice/synthesize', basePayload())
    if (data.error) { capStore.setMessage(`配音合成失败：${data.error}`, 'error'); return }
    result.value = data.synthesis || null
    doneSynthesize.value = true
    capStore.setMessage('配音合成完成', 'success')
  } finally {
    loadingSynthesize.value = false
  }
}

async function buildTimeline() {
  if (loadingTimeline.value) return
  loadingTimeline.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/audio_voice/build_track', {
      output_audio: input.timeline_output, dry_run: input.dry_run,
    })
    if (data.error) { capStore.setMessage(`旁白轨生成失败：${data.error}`, 'error'); return }
    result.value = data.timeline || null
    doneTimeline.value = true
    capStore.setMessage('旁白轨生成完成', 'success')
  } finally {
    loadingTimeline.value = false
  }
}

async function pickBgm() {
  if (loadingBgm.value) return
  loadingBgm.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/audio_voice/pick_bgm', {
      mood: input.mood, bgm_provider: input.bgm_provider, bgm_library_dir: input.bgm_library_dir,
    })
    if (data.error) { capStore.setMessage(`自动配乐失败：${data.error}`, 'error'); return }
    result.value = data.pick || null
    doneBgm.value = true
    if (data.pick?.selected_track) input.bgm_audio = data.pick.selected_track
    capStore.setMessage('已自动选中 BGM', 'success')
  } finally {
    loadingBgm.value = false
  }
}

async function mix() {
  if (loadingMix.value) return
  loadingMix.value = true
  try {
    const data = await apiStore.api('POST', '/api/capabilities/audio_voice/mix_master', {
      ...basePayload(), mood: input.mood,
      input_video: input.master_input, narration_audio: input.timeline_output,
      bgm_audio: input.bgm_audio, auto_pick_bgm: input.auto_pick_bgm,
      output_video: input.mix_output, replace_master: input.replace_master,
      origin_volume: input.origin_volume, narration_volume: input.narration_volume,
      bgm_volume: input.bgm_volume, enable_ducking: input.enable_ducking,
    })
    if (data.error) { capStore.setMessage(`成片混音失败：${data.error}`, 'error'); return }
    result.value = data.mix || null
    doneMix.value = true
    capStore.setMessage('成片混音完成', 'success')
  } finally {
    loadingMix.value = false
  }
}

async function runPipeline() {
  if (running.value) return
  running.value = true; progress.value = 0; result.value = null
  const payload = {
    ...basePayload(), mood: input.mood,
    output_audio: input.timeline_output, input_video: input.master_input,
    bgm_audio: input.bgm_audio, auto_pick_bgm: input.auto_pick_bgm,
    bgm_provider: input.bgm_provider, bgm_library_dir: input.bgm_library_dir,
    output_video: input.mix_output, replace_master: input.replace_master,
    origin_volume: input.origin_volume, narration_volume: input.narration_volume,
    bgm_volume: input.bgm_volume, enable_ducking: input.enable_ducking,
  }
  const data = await apiStore.api('POST', '/api/capabilities/audio_voice/run', payload)
  if (data.error) { running.value = false; capStore.setMessage(`音频流水线启动失败：${data.error}`, 'error'); return }
  capStore.setMessage('音频流水线任务已提交', 'info')
  const job = await waitForJob(data.job_id, j => { progress.value = j.progress || 0 }, 3 * 60 * 60 * 1000)
  running.value = false
  if (job.status === 'error') { capStore.setMessage(`音频流水线失败：${job.error}`, 'error'); return }
  if (job.status === 'cancelled') { capStore.setMessage('音频流水线已取消', 'warning'); return }
  result.value = job.result || null
  donePipeline.value = true
  capStore.setMessage('音频流水线完成', 'success')
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.form-row label { width: 90px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 6px; flex-wrap: wrap; }
.btn-row-sticky { position: sticky; bottom: 0; background: var(--bg); padding: 12px 0; border-top: 1px solid var(--border); z-index: 5; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
.btn-done { border-color: var(--success, #48c78e); color: var(--success, #48c78e); }
.btn-done:hover { background: rgba(72, 199, 142, 0.1); }
</style>
