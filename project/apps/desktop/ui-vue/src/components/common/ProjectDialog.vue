<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="appStore.showInit = false">
      <div class="modal">
        <div class="modal-title">
          {{ appStore.initMode === 'new' ? labels.project.new : labels.project.open }}
        </div>

        <!-- 新建项目 -->
        <template v-if="appStore.initMode === 'new'">
          <FormField
            :label="labels.project.projectName"
          >
            <input
              v-model="appStore.initProjectName"
              class="form-input"
              :placeholder="labels.project.projectNamePlaceholder"
            />
          </FormField>

          <FormField
            :label="labels.project.videosDir"
            :error="v.getError('videosDir')"
          >
            <div class="form-row">
              <input v-model="appStore.initVideosDir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('initVideosDir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </FormField>

          <FormField
            :label="labels.project.projectDir"
            :error="v.getError('projectDir')"
          >
            <div class="form-row">
              <input v-model="appStore.initProjectDir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('initProjectDir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </FormField>
        </template>

        <!-- 打开项目 -->
        <template v-else>
          <FormField
            :label="labels.project.projectDir"
            :error="v.getError('openDir')"
          >
            <div class="form-row">
              <input v-model="appStore.initOpenDir" class="form-input" readonly />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('initOpenDir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </FormField>
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
import { useValidation } from '../../composables/useValidation.js'
import labels from '../../i18n/labels.js'
import FormField from './FormField.vue'

const router = useRouter()
const appStore = useAppStore()

const v = useValidation({
  videosDir: [{ type: 'required', message: '请选择素材文件夹' }],
  projectDir: [{ type: 'required', message: '请选择项目保存位置' }],
  openDir: [{ type: 'required', message: '请选择项目文件夹' }],
})

const canSubmit = computed(() => {
  if (appStore.initMode === 'new') {
    return !!appStore.initVideosDir && !!appStore.initProjectDir
  }
  return !!appStore.initOpenDir
})

async function submit() {
  // 校验
  if (appStore.initMode === 'new') {
    const ok = v.validateAll({
      videosDir: appStore.initVideosDir,
      projectDir: appStore.initProjectDir,
      openDir: 'skip', // 不校验
    })
    if (!ok) return
  } else {
    const ok = v.validateAll({
      videosDir: 'skip',
      projectDir: 'skip',
      openDir: appStore.initOpenDir,
    })
    if (!ok) return
  }

  let ok = false
  if (appStore.initMode === 'new') {
    ok = await appStore.createProject(appStore.initVideosDir, appStore.initProjectDir, appStore.initProjectName)
  } else {
    ok = await appStore.openProject(appStore.initOpenDir)
  }
  if (ok) {
    router.push('/create/workflow')
  }
}
</script>
