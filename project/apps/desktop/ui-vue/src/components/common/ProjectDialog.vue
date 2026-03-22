<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="closeDialog">
      <div class="modal">
        <div class="modal-title">
          {{ appStore.initMode === 'new' ? labels.project.new : labels.project.open }}
        </div>

        <!-- 新建项目 -->
        <template v-if="appStore.initMode === 'new'">
          <FormField
            :label="labels.project.projectName"
            hint="用于识别项目，实际文件夹名由系统自动生成"
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
            hint="你的视频素材所在的文件夹"
          >
            <div class="form-row">
              <input v-model="appStore.initVideosDir" class="form-input" />
              <button class="btn btn-ghost btn-sm" @click="appStore.pickFolder('initVideosDir')">
                {{ labels.project.browse }}
              </button>
            </div>
          </FormField>

          <FormField
            :label="labels.project.projectDir"
            :error="v.getError('projectDir')"
            hint="项目文件的保存位置，每个项目独占一个子文件夹"
          >
            <div class="form-row">
              <input v-model="appStore.initProjectDir" class="form-input" />
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
import { computed, onMounted, onUnmounted } from 'vue'
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

function closeDialog() {
  const hasContent = !!(appStore.initProjectName || appStore.initVideosDir || appStore.initProjectDir || appStore.initOpenDir)
  if (hasContent && !confirm('内容尚未保存，确认关闭？')) return
  appStore.showInit = false
}

function onEscKey(e) {
  if (e.key === 'Escape') closeDialog()
}
onMounted(() => window.addEventListener('keydown', onEscKey))
onUnmounted(() => window.removeEventListener('keydown', onEscKey))

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
