<script setup lang="ts">
// 通用状态占位组件：loading/empty/error 三种空态展示。
withDefaults(
  defineProps<{
    kind?: "loading" | "empty" | "error";
    title: string;
    detail?: string;
  }>(),
  {
    kind: "empty",
    detail: "",
  },
);
</script>

<template>
  <div class="ui-state" :class="kind" :role="kind === 'error' ? 'alert' : 'status'">
    <span v-if="kind === 'loading'" class="typing" aria-hidden="true"><i></i><i></i><i></i></span>
    <strong>{{ title }}</strong>
    <p v-if="detail">{{ detail }}</p>
    <slot />
  </div>
</template>
