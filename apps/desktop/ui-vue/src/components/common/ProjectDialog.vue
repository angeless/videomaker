<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="appStore.showInit = false">
      <div class="modal">
        <div class="modal-title">
          {{ appStore.initMode === 'new' ? labels.project.new : labels.project.open }}
        </div>

        <!-- 新建项目 -->
        <template v-if="appStore.initMode === 'new'">
          <div class="form-group">
            <label class="form-label">{{ labels.project.videosDir }}</label>
            <div class="form-row">
              <input v-model="appStore.initVideosDir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('initVideosDir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">{{ labels.project.projectDir }}</label>
            <div class="form-row">
              <input v-model="appStore.initProjectDir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('initProjectDir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </div>
        </template>

        <!-- 打开项目 -->
        <template v-else>
          <div class="form-group">
            <label class="form-label">{{ labels.project.projectDir }}</label>
            <div class="form-row">
              <input v-model="appStore.initOpenDir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('initOpenDir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </div>
        </template>

        <p v-if="appStore.initError" class="text-danger" style="font-size: 13px; margin-top: 8px">
          {{ appStore.initError }}
        </p>

        <div class="modal-actions">
          <button class="btn btn-ghost" @click="appStore.showInit = false">{{ labels.common.cancel }}</button>
          <button
            class="btn btn-primary"
            :disabled="appStore.initLoading || !canSubmit"
            @click="submit"
          >
            {{ appStore.initLoading
              ? (appStore.initMode === 'new' ? labels.project.creating : labels.project.opening)
              : (appStore.initMode === 'new' ? labels.project.create : labels.project.open)
            }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app.js'
import labels from '../../i18n/labels.js'

const router = useRouter()
const appStore = useAppStore()

const canSubmit = computed(() => {
  if (appStore.initMode === 'new') {
    return !!appStore.initVideosDir && !!appStore.initProjectDir
  }
  return !!appStore.initOpenDir
})

async function submit() {
  let ok = false
  if (appStore.initMode === 'new') {
    ok = await appStore.createProject(appStore.initVideosDir, appStore.initProjectDir)
  } else {
    ok = await appStore.openProject(appStore.initOpenDir)
  }
  if (ok) {
    router.push('/production/workflow')
  }
}
</script>
