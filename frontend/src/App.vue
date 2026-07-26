<script setup lang="ts">
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
