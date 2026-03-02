<template>
  <Teleport to="body">
    <div class="modal-overlay">
      <div class="modal" style="min-width: 480px">
        <div class="modal-title">{{ labels.onboarding.title }}</div>

        <!-- 步骤指示 -->
        <div class="onboarding-steps">
          <div
            v-for="(s, i) in stepsData"
            :key="i"
            class="onboarding-dot"
            :class="{ active: step === i, done: step > i }"
          ></div>
        </div>

        <!-- 步骤内容 -->
        <div class="onboarding-content">
          <h3>{{ stepsData[step].title }}</h3>
          <p>{{ stepsData[step].desc }}</p>
        </div>

        <!-- 操作按钮 -->
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="appStore.dismissOnboarding(false)">
            {{ labels.onboarding.skip }}
          </button>
          <div style="flex: 1"></div>
          <button v-if="step > 0" class="btn btn-ghost" @click="step--">
            {{ labels.onboarding.prev }}
          </button>
          <button v-if="step < stepsData.length - 1" class="btn btn-primary" @click="step++">
            {{ labels.onboarding.next }}
          </button>
          <button v-else class="btn btn-success" @click="appStore.dismissOnboarding(true)">
            {{ labels.onboarding.finish }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'
import { useAppStore } from '../../stores/app.js'
import labels from '../../i18n/labels.js'

const appStore = useAppStore()
const step = ref(0)

const stepsData = [
  { title: labels.onboarding.step1Title, desc: labels.onboarding.step1Desc },
  { title: labels.onboarding.step2Title, desc: labels.onboarding.step2Desc },
  { title: labels.onboarding.step3Title, desc: labels.onboarding.step3Desc },
]
</script>

<style scoped>
.onboarding-steps {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
}

.onboarding-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--border);
  transition: background 0.2s;
}

.onboarding-dot.active {
  background: var(--accent);
}

.onboarding-dot.done {
  background: var(--success);
}

.onboarding-content {
  min-height: 100px;
}

.onboarding-content h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.onboarding-content p {
  font-size: 14px;
  color: var(--muted);
  line-height: 1.7;
}
</style>
