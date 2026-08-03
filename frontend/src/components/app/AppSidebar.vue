<script setup lang="ts">
// 应用侧边栏：导航入口、会话历史与健康状态指示。
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useAuthStore } from "@/stores/auth";
import { handleDialogKeydown } from "@/lib/focusTrap";

type Mode =
  | "today"
  | "chat"
  | "interview"
  | "report"
  | "learning"
  | "history"
  | "resume"
  | "review";

const props = defineProps<{
  mode: Mode;
  open: boolean;
}>();

const emit = defineEmits<{
  (e: "select-mode", mode: Mode): void;
  (e: "new-chat"): void;
  (e: "open-settings"): void;
  (e: "close"): void;
}>();

const auth = useAuthStore();

const online = ref<boolean | null>(null);
const sidebarElement = ref<HTMLElement | null>(null);
const isMobile = ref(false);
let mobileQuery: MediaQueryList | null = null;
let syncMobile: (() => void) | null = null;

const avatarInitials = computed(() => {
  if (auth.username) return Array.from(auth.username).slice(0, 2).join("").toUpperCase();
  return "ME";
});

let healthTimer: number | undefined;

async function checkHealth() {
  try {
    // `/ready` is an operator-only dependency probe and requires the deployment
    // key. Browser status only needs the public process liveness endpoint.
    online.value = (await fetch("/health")).ok;
  } catch {
    online.value = false;
  }
}

function selectMode(next: Mode) {
  emit("select-mode", next);
}

// 抽屉打开时按 Escape 关闭(阶段 3 可访问性)
function onKeydown(event: KeyboardEvent) {
  if (props.open && isMobile.value) {
    handleDialogKeydown(event, sidebarElement.value, () => emit("close"));
  }
}

onMounted(() => {
  checkHealth();
  // 健康状态定期刷新(每 60s),保持侧边栏「在线」状态真实
  healthTimer = window.setInterval(checkHealth, 60000);
  window.addEventListener("keydown", onKeydown);
  mobileQuery = window.matchMedia("(max-width: 860px)");
  syncMobile = () => {
    isMobile.value = Boolean(mobileQuery?.matches);
  };
  syncMobile();
  mobileQuery.addEventListener("change", syncMobile);
});

onUnmounted(() => {
  if (healthTimer) window.clearInterval(healthTimer);
  window.removeEventListener("keydown", onKeydown);
  if (syncMobile) mobileQuery?.removeEventListener("change", syncMobile);
});

watch(
  () => props.open,
  (open) => {
    if (open && isMobile.value) nextTick(() => sidebarElement.value?.focus());
  },
);

</script>

<template>
  <aside
    ref="sidebarElement"
    id="sidebar"
    class="sidebar"
    :class="{ open }"
    :aria-hidden="isMobile && !open ? 'true' : undefined"
    :aria-modal="isMobile && open ? 'true' : undefined"
    :role="isMobile ? 'dialog' : undefined"
    :inert="isMobile && !open"
    tabindex="-1"
    aria-label="侧边导航"
  >
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">IL</div>
      <div>
        <strong>Interview Lab</strong>
        <span>AI 面试训练场</span>
      </div>
    </div>

    <button class="new-chat" type="button" @click="emit('new-chat')">
      <i class="ph ph-plus new-chat-icon" aria-hidden="true"></i>
      新建对话
    </button>

    <nav class="sidebar-nav" aria-label="训练工具">
      <p class="nav-label">训练空间</p>
      <button
        v-if="auth.resumeFeatureEnabled"
        class="nav-item"
        :class="{ active: mode === 'resume' }"
        type="button"
        @click="selectMode('resume')"
      >
        <i class="ph ph-file-text nav-icon" aria-hidden="true"></i>
        简历中心
      </button>
      <button
        v-if="auth.reviewFeatureEnabled"
        class="nav-item"
        :class="{ active: mode === 'review' }"
        type="button"
        @click="selectMode('review')"
      >
        <i class="ph ph-waveform nav-icon" aria-hidden="true"></i>
        面试复盘
      </button>
      <button
        class="nav-item"
        :class="{ active: mode === 'today' }"
        type="button"
        @click="selectMode('today')"
      >
        <i class="ph ph-house nav-icon" aria-hidden="true"></i>
        今日训练
      </button>
      <button
        class="nav-item"
        :class="{ active: mode === 'chat' }"
        type="button"
        @click="selectMode('chat')"
      >
        <i class="ph ph-chat-circle nav-icon" aria-hidden="true"></i>
        知识问答
      </button>
      <button
        class="nav-item"
        :class="{ active: mode === 'interview' }"
        type="button"
        @click="selectMode('interview')"
      >
        <i class="ph ph-clipboard-text nav-icon" aria-hidden="true"></i>
        模拟面试
      </button>
      <button
        class="nav-item"
        :class="{ active: mode === 'report' }"
        type="button"
        @click="selectMode('report')"
      >
        <i class="ph ph-chart-line-up nav-icon" aria-hidden="true"></i>
        能力画像
      </button>
      <button
        class="nav-item"
        :class="{ active: mode === 'learning' }"
        type="button"
        @click="selectMode('learning')"
      >
        <i class="ph ph-check nav-icon" aria-hidden="true"></i>
        学习计划
      </button>
      <button
        class="nav-item"
        :class="{ active: mode === 'history' }"
        type="button"
        @click="selectMode('history')"
      >
        <i class="ph ph-clock-counter-clockwise nav-icon" aria-hidden="true"></i>
        历史记录
      </button>
    </nav>

    <div class="knowledge-card">
      <div class="card-heading">
        <span class="pulse-dot" :class="{ offline: online === false }"></span>
        {{ online === null ? "检测中" : online ? "服务在线" : "服务离线" }}
      </div>
      <p>会话、面试与学习按账号隔离保存</p>
    </div>

    <div class="sidebar-footer">
      <button
        class="avatar"
        type="button"
        aria-label="设置头像"
        title="设置头像"
        @click="emit('open-settings')"
      >
        <img v-if="auth.avatarDataUrl" :src="auth.avatarDataUrl" alt="" />
        <span v-else aria-hidden="true">{{ avatarInitials }}</span>
      </button>
      <div class="sidebar-account-copy">
        <strong id="account-name">{{ auth.username || "未登录" }}</strong>
        <span>{{ auth.isAuthenticated ? "已登录" : "本地会话" }}</span>
      </div>
      <div class="sidebar-account-actions">
        <button
          class="sidebar-settings"
          type="button"
          aria-label="打开设置"
          title="设置"
          @click="emit('open-settings')"
        >
          <i class="ph ph-gear" aria-hidden="true"></i>
        </button>
        <button
          v-if="auth.isAuthenticated"
          class="logout-button"
          type="button"
          @click="auth.logout()"
        >
          退出
        </button>
      </div>
    </div>
  </aside>
</template>
