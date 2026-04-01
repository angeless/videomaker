<template>
  <div class="player-controls">
    <!-- Progress bar -->
    <div class="pc-progress" @mousedown="onProgressMouseDown" ref="progressRef">
      <div class="pc-progress-fill" :style="{ width: progressPct + '%' }"></div>
      <div class="pc-progress-head" :style="{ left: progressPct + '%' }"></div>
      <!-- Loop region -->
      <div
        v-if="store.loopIn != null && store.loopOut != null"
        class="pc-loop-region"
        :style="loopRegionStyle"
      ></div>
    </div>

    <!-- Controls row -->
    <div class="pc-row">
      <!-- Left: navigation buttons -->
      <div class="pc-group">
        <button class="pc-btn" @click="emit('back5s')" title="-5s (Shift+Left)">-5s</button>
        <button class="pc-btn" @click="emit('prevFrame')" title="-1帧 (Left)">
          <span class="pc-icon">&#9664;&#9664;</span>
        </button>
        <button class="pc-btn pc-btn-play" @click="emit('togglePlay')" :title="store.isPlaying ? '暂停 (K)' : '播放 (K)'">
          <span v-if="store.isPlaying">&#9646;&#9646;</span>
          <span v-else>&#9654;</span>
        </button>
        <button class="pc-btn" @click="emit('nextFrame')" title="+1帧 (Right)">
          <span class="pc-icon">&#9654;&#9654;</span>
        </button>
        <button class="pc-btn" @click="emit('forward5s')" title="+5s (Shift+Right)">+5s</button>
      </div>

      <!-- Center: timecode -->
      <div class="pc-timecode">
        <span class="pc-time-current">{{ formatSmpte(store.currentTimeMs) }}</span>
        <span class="pc-time-sep">/</span>
        <span class="pc-time-total">{{ formatSmpte(store.durationMs) }}</span>
      </div>

      <!-- Right: speed + volume + IO + fullscreen -->
      <div class="pc-group">
        <!-- Speed -->
        <div class="pc-speed">
          <button class="pc-btn pc-btn-sm" @click="cycleSpeed">{{ store.playbackRate }}x</button>
        </div>

        <!-- I/O Loop -->
        <button
          class="pc-btn pc-btn-sm"
          @click="emit('setLoopIn')"
          :class="{ active: store.loopIn != null }"
          title="入点 (I)"
        >I</button>
        <button
          class="pc-btn pc-btn-sm"
          @click="emit('setLoopOut')"
          :class="{ active: store.loopOut != null }"
          title="出点 (O)"
        >O</button>
        <button
          class="pc-btn pc-btn-sm"
          @click="emit('toggleLoop')"
          :class="{ active: store.isLooping }"
          title="循环 (Cmd+L)"
        >&#128257;</button>

        <!-- Volume -->
        <div class="pc-volume">
          <button class="pc-btn pc-btn-sm" @click="toggleMute" :title="store.isMuted ? '取消静音' : '静音'">
            <span v-if="store.isMuted || store.volume === 0">&#128263;</span>
            <span v-else-if="store.volume < 0.5">&#128264;</span>
            <span v-else>&#128266;</span>
          </button>
          <input
            type="range"
            min="0" max="1" step="0.05"
            :value="store.volume"
            @input="store.volume = parseFloat($event.target.value)"
            class="pc-volume-slider"
          />
        </div>

        <!-- Zoom -->
        <button class="pc-btn pc-btn-sm" @click="emit('zoomReset')" title="适应 (Cmd+0)">
          {{ Math.round(store.zoomLevel * 100) }}%
        </button>

        <!-- Fullscreen -->
        <button class="pc-btn pc-btn-sm" @click="emit('toggleFullscreen')" title="全屏 (F)">
          &#x26F6;
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useReviewStore } from '../../stores/review.js'

const store = useReviewStore()
const emit = defineEmits([
  'togglePlay', 'prevFrame', 'nextFrame', 'back5s', 'forward5s',
  'seek', 'setLoopIn', 'setLoopOut', 'toggleLoop',
  'toggleFullscreen', 'zoomReset',
])

const props = defineProps({
  fps: { type: Number, default: 30 },
})

const progressRef = defineModel('progressRef')

// ── Progress ──
const progressPct = computed(() => {
  if (!store.durationMs) return 0
  return (store.currentTimeMs / store.durationMs) * 100
})

const loopRegionStyle = computed(() => {
  if (store.loopIn == null || store.loopOut == null || !store.durationMs) return {}
  const left = (store.loopIn / store.durationMs) * 100
  const width = ((store.loopOut - store.loopIn) / store.durationMs) * 100
  return { left: left + '%', width: width + '%' }
})

function onProgressMouseDown(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  emit('seek', Math.round(pct * store.durationMs))

  function onMouseMove(e2) {
    const pct2 = Math.max(0, Math.min(1, (e2.clientX - rect.left) / rect.width))
    emit('seek', Math.round(pct2 * store.durationMs))
  }
  function onMouseUp() {
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

// ── Speed ──
const SPEEDS = [0.25, 0.5, 1, 1.5, 2, 4]

function cycleSpeed() {
  const idx = SPEEDS.indexOf(store.playbackRate)
  store.playbackRate = SPEEDS[(idx + 1) % SPEEDS.length]
}

// ── Volume ──
function toggleMute() {
  store.isMuted = !store.isMuted
}

// ── SMPTE Timecode ──
function formatSmpte(ms) {
  if (!ms || ms < 0) return '00:00:00:00'
  const totalS = ms / 1000
  const h = Math.floor(totalS / 3600)
  const m = Math.floor((totalS % 3600) / 60)
  const s = Math.floor(totalS % 60)
  const f = Math.floor((totalS % 1) * props.fps)
  return [
    String(h).padStart(2, '0'),
    String(m).padStart(2, '0'),
    String(s).padStart(2, '0'),
    String(f).padStart(2, '0'),
  ].join(':')
}
</script>

<style scoped>
.player-controls {
  background: #1a1a1a;
  padding: 4px 8px 6px;
  user-select: none;
}

.pc-progress {
  position: relative;
  height: 6px;
  background: #333;
  border-radius: 3px;
  cursor: pointer;
  margin-bottom: 6px;
}

.pc-progress-fill {
  position: absolute;
  height: 100%;
  background: #3b82f6;
  border-radius: 3px;
  pointer-events: none;
}

.pc-progress-head {
  position: absolute;
  top: -3px;
  width: 12px;
  height: 12px;
  background: #fff;
  border-radius: 50%;
  transform: translateX(-50%);
  pointer-events: none;
}

.pc-loop-region {
  position: absolute;
  height: 100%;
  background: rgba(234, 179, 8, 0.3);
  border-left: 1px solid #eab308;
  border-right: 1px solid #eab308;
  pointer-events: none;
}

.pc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.pc-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.pc-btn {
  background: none;
  border: none;
  color: #ccc;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 0.8rem;
  line-height: 1;
}

.pc-btn:hover {
  background: #333;
  color: #fff;
}

.pc-btn.active {
  color: #eab308;
}

.pc-btn-play {
  font-size: 1rem;
  padding: 4px 10px;
}

.pc-btn-sm {
  font-size: 0.7rem;
  padding: 2px 6px;
}

.pc-icon {
  font-size: 0.65rem;
  letter-spacing: -2px;
}

.pc-timecode {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 0.75rem;
  color: #ccc;
  white-space: nowrap;
}

.pc-time-sep {
  margin: 0 4px;
  color: #666;
}

.pc-speed button {
  min-width: 36px;
}

.pc-volume {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pc-volume-slider {
  width: 60px;
  height: 3px;
  accent-color: #3b82f6;
}
</style>
