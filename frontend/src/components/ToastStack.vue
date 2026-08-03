<script setup lang="ts">
// 全局轻提示堆叠：渲染 toast 列表并处理自动消失与手动关闭。
import { useToastStore } from "@/stores/toast";

const toasts = useToastStore();
</script>

<template>
  <div class="toast-stack" aria-live="polite" aria-atomic="false">
    <div
      v-for="toast in toasts.toasts"
      :key="toast.id"
      class="toast"
      :class="toast.kind"
      role="status"
    >
      <span>{{ toast.message }}</span>
      <button
        type="button"
        class="toast-close"
        aria-label="关闭通知"
        @click="toasts.dismiss(toast.id)"
      >
        <i class="ph ph-x" aria-hidden="true"></i>
      </button>
    </div>
  </div>
</template>
