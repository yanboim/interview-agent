<script setup lang="ts">
// 产品端主视图：侧边栏 + 顶栏 + 各功能面板（聊天/面试/学习/简历/复盘等）。
import { computed, defineAsyncComponent, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useThemeStore } from "@/stores/theme";
import { fetchDueReminders } from "@/api/client";
import { useToastStore } from "@/stores/toast";
import { startClientObservability } from "@/lib/observability";
import AppSidebar from "@/components/app/AppSidebar.vue";
import AppTopbar from "@/components/app/AppTopbar.vue";
const TodayPanel = defineAsyncComponent(() => import("@/components/app/TodayPanel.vue"));
const ChatPanel = defineAsyncComponent(() => import("@/components/app/ChatPanel.vue"));
const InterviewPanel = defineAsyncComponent(
  () => import("@/components/app/InterviewPanel.vue"),
);
const ProfilePanel = defineAsyncComponent(() => import("@/components/app/ProfilePanel.vue"));
const LearningPanel = defineAsyncComponent(() => import("@/components/app/LearningPanel.vue"));
const HistoryPanel = defineAsyncComponent(() => import("@/components/app/HistoryPanel.vue"));
const ResumePanel = defineAsyncComponent(() => import("@/components/app/ResumePanel.vue"));
const ReviewPanel = defineAsyncComponent(() => import("@/components/app/ReviewPanel.vue"));
const AuthOverlay = defineAsyncComponent(() => import("@/components/app/AuthOverlay.vue"));
const AppSettingsDialog = defineAsyncComponent(
  () => import("@/components/app/AppSettingsDialog.vue"),
);
const GoalSetupDialog = defineAsyncComponent(
  () => import("@/components/app/GoalSetupDialog.vue"),
);
const RecoveryCodeDialog = defineAsyncComponent(
  () => import("@/components/app/RecoveryCodeDialog.vue"),
);

type Mode =
  | "today"
  | "chat"
  | "interview"
  | "report"
  | "learning"
  | "history"
  | "resume"
  | "review";

const auth = useAuthStore();
const chat = useChatStore();
const theme = useThemeStore();
const toast = useToastStore();
const route = useRoute();
const router = useRouter();

const sidebarOpen = ref(false);
const settingsOpen = ref(false);
const mode = computed(() => (route.meta.mode as Mode | undefined) || "today");

const showAuth = computed(
  () => auth.authRequired && !auth.isAuthenticated && !auth.initializing,
);
const showGoal = computed(
  () =>
    auth.isAuthenticated
    && !auth.pendingRecoveryCode
    && !auth.hasInterviewGoal
    && !showAuth.value,
);
const appBlocked = computed(
  () =>
    showAuth.value
    || showGoal.value
    || Boolean(auth.pendingRecoveryCode)
    || settingsOpen.value,
);

const modePath: Record<Mode, string> = {
  today: "/today",
  chat: "/chat",
  interview: "/interviews",
  report: "/profile",
  learning: "/learning",
  history: "/history",
  resume: "/resumes",
  review: "/reviews",
};

async function setMode(next: Mode) {
  localStorage.setItem("interview-lab-mode", next);
  sidebarOpen.value = false;
  await router.push(
    next === "chat"
      ? `/chat/${encodeURIComponent(auth.sessionId)}`
      : modePath[next],
  );
}

async function startNewChat() {
  chat.clear();
  auth.newSession();
  await router.push(`/chat/${encodeURIComponent(auth.sessionId)}`);
}

watch(
  () => route.params.sessionId,
  (sessionId) => {
    if (typeof sessionId !== "string" || !sessionId || sessionId === auth.sessionId) return;
    auth.sessionId = sessionId;
    chat.initForSession(sessionId);
    chat.loadHistory(auth.userId, sessionId);
  },
  { immediate: true },
);

onMounted(async () => {
  await auth.initialize();
  startClientObservability(
    () => auth.userId,
    () => !auth.authRequired || auth.isAuthenticated,
  );
  const sessionId = route.params.sessionId;
  if (typeof sessionId === "string" && sessionId && sessionId !== auth.sessionId) {
    auth.sessionId = sessionId;
    chat.initForSession(sessionId);
    await chat.loadHistory(auth.userId, sessionId);
  }
  if (!auth.authRequired || auth.isAuthenticated) {
    void fetchDueReminders(auth.userId)
      .then((reminders) => {
        if (!reminders.due || !reminders.items.length) return;
        const first = reminders.items[0];
        toast.show(`今日复习：${first.title}`, "info", 5000);
        const notificationKey = `interview-lab-notified:${reminders.local_date}`;
        if (
          "Notification" in window
          && Notification.permission === "granted"
          && !localStorage.getItem(notificationKey)
        ) {
          new Notification("Interview Lab 今日复习", {
            body: first.action,
            icon: "/static/favicon.svg",
          });
          localStorage.setItem(notificationKey, "1");
        }
      })
      .catch(() => {
        // 提醒不可用不阻塞训练空间。
      });
  }
});

const topicTitle = computed(() =>
  mode.value === "today"
    ? "今日训练"
    : mode.value === "chat"
    ? "知识问答"
    : mode.value === "interview"
      ? "模拟面试"
      : mode.value === "report"
        ? "能力画像"
        : mode.value === "learning"
          ? "学习计划"
          : mode.value === "resume"
            ? "简历中心"
            : mode.value === "review"
              ? "面试复盘"
            : "历史记录",
);
</script>

<template>
  <div class="app-shell" :inert="appBlocked">
    <AppSidebar
      :mode="mode"
      :open="sidebarOpen"
      @select-mode="setMode"
      @new-chat="startNewChat"
      @open-settings="settingsOpen = true"
      @close="sidebarOpen = false"
    />

    <div
      class="sidebar-backdrop"
      :class="{ open: sidebarOpen }"
      @click="sidebarOpen = false"
    />

    <main class="main" :inert="sidebarOpen">
      <AppTopbar
        :title="topicTitle"
        :dark="theme.isDark"
        :menu-open="sidebarOpen"
        :chat-mode="mode === 'chat'"
        @toggle-theme="theme.set(theme.isDark ? 'light' : 'dark')"
        @open-menu="sidebarOpen = !sidebarOpen"
        @new-chat="startNewChat"
      />

      <template v-if="!auth.initializing && (!auth.authRequired || auth.isAuthenticated)">
        <TodayPanel v-if="mode === 'today'" />
        <ChatPanel v-else-if="mode === 'chat'" />
        <InterviewPanel
          v-else-if="mode === 'interview'"
          mode="interview"
          @go-report="setMode('report')"
          @go-learning="setMode('learning')"
        />
        <ProfilePanel v-else-if="mode === 'report'" />
        <LearningPanel v-else-if="mode === 'learning'" />
        <ResumePanel v-else-if="mode === 'resume' && auth.resumeFeatureEnabled" />
        <ReviewPanel v-else-if="mode === 'review' && auth.reviewFeatureEnabled" />
        <div v-else-if="mode === 'resume'" class="app-initializing" role="status">
          简历功能尚未启用
        </div>
        <div v-else-if="mode === 'review'" class="app-initializing" role="status">
          面试复盘尚未启用
        </div>
        <HistoryPanel v-else-if="mode === 'history'" />
      </template>
      <div v-else class="app-initializing" aria-live="polite">正在准备训练空间…</div>
    </main>

    <AuthOverlay v-if="showAuth" />
    <RecoveryCodeDialog v-else-if="auth.pendingRecoveryCode" />
    <GoalSetupDialog
      v-else-if="showGoal"
    />
    <AppSettingsDialog v-if="settingsOpen" @close="settingsOpen = false" />
  </div>
</template>
