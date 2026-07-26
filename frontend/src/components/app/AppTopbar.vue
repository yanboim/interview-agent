<script setup lang="ts">
import { ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { confirm } from "@/composables/confirm";
import { deleteConversation } from "@/api/client";

defineProps<{
  title: string;
  dark: boolean;
  menuOpen: boolean;
  chatMode: boolean;
}>();

const emit = defineEmits<{
  (e: "toggle-theme"): void;
  (e: "open-menu"): void;
  (e: "new-chat"): void;
}>();

const auth = useAuthStore();
const online = ref(true);
const actionsOpen = ref(false);

// 顶栏也读取一次健康状态用于显示「在线」
async function checkOnline() {
  try {
    online.value = (await fetch("/health")).ok;
  } catch {
    online.value = false;
  }
}
checkOnline();

async function clearChat() {
  // 阶段 1:清空 = 删除服务端会话,明确告知用户并二次确认
  const confirmed = await confirm({
    title: "清空当前对话？",
    message: "这将删除服务端保存的本次会话记录,且无法恢复。",
    detail: auth.sessionId,
    confirmText: "删除会话",
    danger: true,
  });
  if (!confirmed) return;
  actionsOpen.value = false;
  try {
    await deleteConversation(auth.userId, auth.sessionId);
  } catch {
    // 清理不应依赖后端可用性
  }
  emit("new-chat");
}
</script>

<template>
  <header class="topbar">
    <button
      class="icon-button menu-button"
      type="button"
      :aria-expanded="menuOpen"
      aria-controls="sidebar"
      :aria-label="menuOpen ? '关闭菜单' : '打开菜单'"
      @click="emit('open-menu')"
    >
      <i class="ph ph-list" aria-hidden="true"></i>
    </button>
    <div class="topic">
      <span>{{ title }}</span>
      <small>
        <i :class="{ offline: !online }"></i>
        {{ online ? "服务可用" : "连接异常" }}
      </small>
    </div>
    <div class="top-actions">
      <span class="model-pill">私人知识库</span>
      <button
        class="icon-button"
        type="button"
        :aria-label="dark ? '切换到浅色' : '切换到深色'"
        :title="dark ? '切换到浅色' : '切换到深色'"
        @click="emit('toggle-theme')"
      >
        <i class="ph" :class="dark ? 'ph-sun' : 'ph-moon'" aria-hidden="true"></i>
      </button>
      <div v-if="chatMode" class="top-more">
        <button
          class="icon-button"
          type="button"
          aria-label="对话操作"
          :aria-expanded="actionsOpen"
          @click="actionsOpen = !actionsOpen"
        >
          <i class="ph ph-dots-three" aria-hidden="true"></i>
        </button>
        <div v-if="actionsOpen" class="top-more-menu">
          <button type="button" @click="actionsOpen = false; emit('new-chat')">
            <i class="ph ph-plus" aria-hidden="true"></i>
            新建对话
          </button>
          <button class="danger-action" type="button" @click="clearChat">
            <i class="ph ph-trash" aria-hidden="true"></i>
            删除当前会话
          </button>
        </div>
      </div>
    </div>
  </header>
</template>
