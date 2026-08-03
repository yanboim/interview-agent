<script setup lang="ts">
// 应用根组件：挂载时初始化主题、认证与前端可观测性，按登录态切换视图。
import { onMounted } from "vue";
import { RouterView } from "vue-router";
import ToastStack from "@/components/ToastStack.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useThemeStore } from "@/stores/theme";

const theme = useThemeStore();
onMounted(() => theme.init());
</script>

<template>
  <RouterView />
  <ToastStack />
  <ConfirmDialog />
</template>
