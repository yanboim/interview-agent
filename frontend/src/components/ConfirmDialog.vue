<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { answerConfirm, useConfirm } from "@/composables/confirm";
import { handleDialogKeydown } from "@/lib/focusTrap";

const state = useConfirm();
const cardRef = ref<HTMLElement | null>(null);

function close(confirmed: boolean) {
  answerConfirm(confirmed);
}

function onKeydown(event: KeyboardEvent) {
  if (!state.open) return;
  handleDialogKeydown(event, cardRef.value, () => close(false));
}

// 对话框打开期间监听键盘;焦点陷阱由 autofocus + Tab 在卡片内循环近似处理。
watch(
  () => state.open,
  (open) => {
    if (open) {
      window.addEventListener("keydown", onKeydown);
    } else {
      window.removeEventListener("keydown", onKeydown);
    }
  },
);

onMounted(() => {
  if (state.open) window.addEventListener("keydown", onKeydown);
});
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <Teleport to="body">
    <div v-if="state.open" class="confirm-overlay" role="dialog" aria-modal="true">
      <div ref="cardRef" class="confirm-card">
        <h3>{{ state.options.title }}</h3>
        <p v-if="state.options.message">{{ state.options.message }}</p>
        <div v-if="state.options.detail" class="confirm-detail">
          {{ state.options.detail }}
        </div>
        <div class="confirm-actions">
          <button
            type="button"
            class="confirm-cancel"
            autofocus
            @click="close(false)"
          >
            {{ state.options.cancelText || "取消" }}
          </button>
          <button
            type="button"
            class="confirm-ok"
            :class="{ danger: state.options.danger }"
            @click="close(true)"
          >
            {{ state.options.confirmText || "确认" }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
