<template>
  <div>
    <h3>配乐配音</h3>

    <div class="cap-section">
      <div class="cap-subtitle">基础设置</div>
      <div class="form-row"><label>氛围</label><input v-model="input.mood" class="form-input" placeholder="travel_story" /></div>
      <div class="form-row"><label>TTS 提供商</label><input v-model="input.provider" class="form-input" placeholder="elevenlabs" /></div>
      <div class="form-row"><label>Voice ID</label><input v-model="input.voice_id" class="form-input" /></div>
      <div class="form-row"><label>API Key</label><input v-model="input.api_key" type="password" class="form-input" /></div>
      <div class="form-row"><label>模型</label><input v-model="input.model_id" class="form-input" /></div>
      <div class="form-row"><label>Dry-run</label><input type="checkbox" v-model="input.dry_run" /></div>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">BGM 设置</div>
      <div class="form-row"><label>BGM 提供商</label><input v-model="input.bgm_provider" class="form-input" placeholder="local_library" /></div>
      <div class="form-row"><label>BGM 目录</label><input v-model="input.bgm_library_dir" class="form-input" /></div>
      <div class="form-row"><label>自动选曲</label><input type="checkbox" v-model="input.auto_pick_bgm" /></div>
    </div>

    <div class="cap-section">
      <div class="cap-subtitle">混音参数</div>
      <div class="form-row"><label>原声音量</label><input v-model.number="input.origin_volume" type="number" step="0.05" class="form-input" /></div>
      <div class="form-row"><label>旁白音量</label><input v-model.number="input.narration_volume" type="number" step="0.05" class="form-input" /></div>
      <div class="form-row"><label>BGM 音量</label><input v-model.number="input.bgm_volume" type="number" step="0.05" class="form-input" /></div>
      <div class="form-row"><label>替换成片</label><input type="checkbox" v-model="input.replace_master" /></div>
    </div>

    <div class="btn-row">
      <button class="btn btn-sm" @click="plan" :disabled="!appStore.projectDir">规划</button>
      <button class="btn btn-sm" @click="synthesize" :disabled="!appStore.projectDir">合成配音</button>
      <button class="btn btn-sm" @click="buildTimeline" :disabled="!appStore.projectDir">生成旁白轨</button>
      <button class="btn btn-sm" @click="pickBgm" :disabled="!appStore.projectDir">选配乐</button>
      <button class="btn btn-sm" @click="mix" :disabled="!appStore.projectDir">混音</button>
      <button class="btn btn-primary btn-sm" @click="runPipeline" :disabled="!appStore.projectDir || running">
        {{ running ? '执行中…' : '一键全流程' }}
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

function basePayload() {
  return {
    mood: input.mood, provider: input.provider, voice_id: input.voice_id,
    api_key: input.api_key, model_id: input.model_id, output_dir: input.output_dir,
    dry_run: input.dry_run,
  }
}

async function plan() {
  const data = await apiStore.api('POST', '/api/capabilities/audio_voice/plan', { mood: input.mood })
  if (data.error) { capStore.setMessage(`配乐配音规划失败：${data.error}`, 'error'); return }
  result.value = data.plan || null
  capStore.setMessage('已生成配乐和配音规划', 'success')
}

async function synthesize() {
  const data = await apiStore.api('POST', '/api/capabilities/audio_voice/synthesize', basePayload())
  if (data.error) { capStore.setMessage(`配音合成失败：${data.error}`, 'error'); return }
  result.value = data.synthesis || null
  capStore.setMessage('配音合成完成', 'success')
}

async function buildTimeline() {
  const data = await apiStore.api('POST', '/api/capabilities/audio_voice/build_track', {
    output_audio: input.timeline_output, dry_run: input.dry_run,
  })
  if (data.error) { capStore.setMessage(`旁白轨生成失败：${data.error}`, 'error'); return }
  result.value = data.timeline || null
  capStore.setMessage('旁白轨生成完成', 'success')
}

async function pickBgm() {
  const data = await apiStore.api('POST', '/api/capabilities/audio_voice/pick_bgm', {
    mood: input.mood, bgm_provider: input.bgm_provider, bgm_library_dir: input.bgm_library_dir,
  })
  if (data.error) { capStore.setMessage(`自动配乐失败：${data.error}`, 'error'); return }
  result.value = data.pick || null
  if (data.pick?.selected_track) input.bgm_audio = data.pick.selected_track
  capStore.setMessage('已自动选中 BGM', 'success')
}

async function mix() {
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
  capStore.setMessage('成片混音完成', 'success')
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
  capStore.setMessage(input.dry_run ? '音频流水线 dry-run 完成' : '音频流水线完成', 'success')
}
</script>

<style scoped>
h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.cap-section { margin-bottom: 20px; }
.cap-subtitle { font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.form-row label { width: 90px; font-size: 12px; color: var(--muted); flex-shrink: 0; }
.btn-row { display: flex; gap: 6px; flex-wrap: wrap; }
.result-pre { background: var(--surface2); padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
</style>
