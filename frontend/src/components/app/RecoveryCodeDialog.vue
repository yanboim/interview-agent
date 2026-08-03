<script setup lang="ts">
// 恢复码对话框：注册/重置后展示一次性恢复码并提示妥善保存。
import { ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { handleDialogKeydown } from "@/lib/focusTrap";

const auth = useAuthStore();
const toast = useToastStore();
const dialogRef = ref<HTMLElement | null>(null);

async function copyCode() {
  try {
    await navigator.clipboard.writeText(auth.pendingRecoveryCode);
    toast.show("恢复码已复制", "success");
  } catch {
    toast.show("复制失败，请手动保存", "error");
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="auth-overlay" role="presentation">
      <section
        ref="dialogRef"
        class="auth-card recovery-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="recovery-title"
        @keydown="handleDialogKeydown($event, dialogRef)"
      >
        <span class="eyebrow">账号恢复</span>
        <h2 id="recovery-title">立即保存你的恢复码</h2>
        <p>忘记密码时需要此恢复码。服务端只保存摘要，关闭后无法再次查看原码。</p>
        <code class="recovery-code">{{ auth.pendingRecoveryCode }}</code>
        <button class="text-action" type="button" @click="copyCode">复制恢复码</button>
        <button class="primary-action" type="button" @click="auth.acknowledgeRecoveryCode()">
          我已安全保存
        </button>
      </section>
    </div>
  </Teleport>
</template>
