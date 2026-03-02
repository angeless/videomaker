<template>
  <div class="stepper">
    <template v-for="(label, i) in steps" :key="i">
      <div
        class="stepper-step"
        :class="{
          active: (i + 1) === active,
          completed: (i + 1) < current,
          disabled: (i + 1) > current + 1,
        }"
        @click="(i + 1) <= current + 1 ? $emit('select', i + 1) : null"
      >
        <div class="stepper-num">
          <span v-if="(i + 1) < current">✓</span>
          <span v-else>{{ i + 1 }}</span>
        </div>
        <span class="stepper-label">{{ label }}</span>
      </div>
      <div
        v-if="i < steps.length - 1"
        class="stepper-connector"
        :class="{ completed: (i + 1) < current }"
      ></div>
    </template>
  </div>
</template>

<script setup>
defineProps({
  steps: { type: Array, required: true },
  current: { type: Number, default: 1 },
  active: { type: Number, default: 1 },
})

defineEmits(['select'])
</script>
