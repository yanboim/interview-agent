<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useToastStore } from "@/stores/toast";
import { confirm } from "@/composables/confirm";
import {
  archiveConversations,
  deleteConversation,
  fetchConversations,
  renameConversation,
} from "@/api/client";
import type { ConversationMeta } from "@/types";
import UiButton from "@/components/ui/UiButton.vue";
import UiState from "@/components/ui/UiState.vue";

const auth = useAuthStore();
const chat = useChatStore();
const router = useRouter();
const toast = useToastStore();

const sessions = ref<ConversationMeta[]>([]);
const loading = ref(true);
const loadError = ref("");
const search = ref("");
const includeArchived = ref(false);
const selectedIds = ref<string[]>([]);
const editingId = ref("");
const titleDraft = ref("");

const filteredSessions = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  if (!query) return sessions.value;
  return sessions.value.filter((session) =>
    (session.title || session.session_id).toLocaleLowerCase().includes(query),
  );
});

const groupedSessions = computed(() => {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const dateKey = (value: Date) =>
    `${value.getFullYear()}-${value.getMonth()}-${value.getDate()}`;
  const groups: Array<{ label: string; items: ConversationMeta[] }> = [];

  for (const session of filteredSessions.value) {
    const updated = new Date(session.updated_at);
    const label = session.archived_at
      ? "已归档"
      : dateKey(updated) === dateKey(today)
        ? "今天"
        : dateKey(updated) === dateKey(yesterday)
          ? "昨天"
          : "更早";
    let group = groups.find((item) => item.label === label);
    if (!group) {
      group = { label, items: [] };
      groups.push(group);
    }
    group.items.push(session);
  }
  return groups;
});

function formatUpdatedAt(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function loadSessions() {
  loading.value = true;
  loadError.value = "";
  try {
    sessions.value = await fetchConversations(auth.userId, includeArchived.value);
    selectedIds.value = selectedIds.value.filter((id) =>
      sessions.value.some((session) => session.session_id === id),
    );
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "历史记录加载失败";
  } finally {
    loading.value = false;
  }
}

function toggleSelection(sessionId: string) {
  selectedIds.value = selectedIds.value.includes(sessionId)
    ? selectedIds.value.filter((id) => id !== sessionId)
    : [...selectedIds.value, sessionId];
}

async function bulkArchive() {
  if (!selectedIds.value.length) return;
  const selected = sessions.value.filter((session) =>
    selectedIds.value.includes(session.session_id),
  );
  const restore = selected.every((session) => Boolean(session.archived_at));
  try {
    await archiveConversations(auth.userId, selectedIds.value, !restore);
    selectedIds.value = [];
    await loadSessions();
    toast.show(restore ? "会话已恢复" : "会话已归档", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "批量操作失败", "error");
  }
}

function startRename(session: ConversationMeta) {
  editingId.value = session.session_id;
  titleDraft.value = session.title || "";
}

async function saveRename(session: ConversationMeta) {
  const title = titleDraft.value.trim();
  if (!title) return;
  try {
    const updated = await renameConversation(auth.userId, session.session_id, title);
    sessions.value = sessions.value.map((item) =>
      item.session_id === updated.session_id ? updated : item,
    );
    editingId.value = "";
    toast.show("会话已重命名", "success", 1600);
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "重命名失败", "error");
  }
}

async function removeSession(session: ConversationMeta) {
  const accepted = await confirm({
    title: "删除该会话？",
    message: "会话及其中的全部消息将被永久删除。",
    detail: session.title,
    confirmText: "删除",
    danger: true,
  });
  if (!accepted) return;
  try {
    await deleteConversation(auth.userId, session.session_id);
    sessions.value = sessions.value.filter((item) => item.session_id !== session.session_id);
    selectedIds.value = selectedIds.value.filter((id) => id !== session.session_id);
    if (session.session_id === auth.sessionId) auth.newSession();
    toast.show("会话已删除", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "删除失败", "error");
  }
}

async function toggleArchive(session: ConversationMeta) {
  try {
    await archiveConversations(auth.userId, [session.session_id], !session.archived_at);
    await loadSessions();
    toast.show(session.archived_at ? "会话已恢复" : "会话已归档", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "操作失败", "error");
  }
}

async function openSession(sessionId: string) {
  localStorage.setItem("interview-lab-mode", "chat");
  await router.push(`/chat/${encodeURIComponent(sessionId)}`);
}

async function startNewChat() {
  chat.clear();
  auth.newSession();
  localStorage.setItem("interview-lab-mode", "chat");
  await router.push(`/chat/${encodeURIComponent(auth.sessionId)}`);
}

watch(includeArchived, loadSessions);
onMounted(loadSessions);
</script>

<template>
  <section class="conversation-history-panel">
    <header class="conversation-history-heading">
      <div>
        <span class="eyebrow">训练档案</span>
        <h1>历史记录</h1>
        <p>集中查找、整理和继续过去的知识问答。</p>
      </div>
      <UiButton @click="startNewChat">
        <i class="ph ph-plus" aria-hidden="true"></i>
        新建对话
      </UiButton>
    </header>

    <div class="conversation-history-toolbar">
      <label class="conversation-history-search">
        <i class="ph ph-magnifying-glass" aria-hidden="true"></i>
        <span class="sr-only">搜索历史记录</span>
        <input v-model="search" type="search" placeholder="搜索标题或关键词" />
      </label>
      <label class="conversation-history-archive-toggle">
        <input v-model="includeArchived" type="checkbox" />
        显示已归档
      </label>
      <UiButton
        v-if="selectedIds.length"
        variant="text"
        @click="bulkArchive"
      >
        批量处理（{{ selectedIds.length }}）
      </UiButton>
    </div>

    <UiState
      v-if="loading"
      kind="loading"
      title="正在加载历史记录…"
    />
    <UiState
      v-else-if="loadError"
      kind="error"
      title="历史记录加载失败"
      :detail="loadError"
    >
      <UiButton variant="text" @click="loadSessions">重新加载</UiButton>
    </UiState>
    <UiState
      v-else-if="!sessions.length"
      kind="empty"
      title="还没有历史记录"
      detail="完成第一次知识问答后，会话会保存在这里。"
    >
      <UiButton variant="text" @click="startNewChat">开始提问</UiButton>
    </UiState>
    <UiState
      v-else-if="!filteredSessions.length"
      kind="empty"
      title="没有匹配的记录"
      detail="尝试更换搜索关键词。"
    />

    <div v-else class="conversation-history-groups">
      <section
        v-for="group in groupedSessions"
        :key="group.label"
        class="conversation-history-group"
      >
        <h2>{{ group.label }} <span>{{ group.items.length }}</span></h2>
        <div class="conversation-history-list">
          <article
            v-for="session in group.items"
            :key="session.session_id"
            class="conversation-history-row"
            :class="{ archived: session.archived_at }"
          >
            <input
              type="checkbox"
              :checked="selectedIds.includes(session.session_id)"
              :aria-label="`选择会话：${session.title}`"
              @change="toggleSelection(session.session_id)"
            />
            <div class="conversation-history-main">
              <form
                v-if="editingId === session.session_id"
                @submit.prevent="saveRename(session)"
              >
                <input
                  v-model="titleDraft"
                  maxlength="60"
                  aria-label="会话标题"
                  autofocus
                  @keydown.escape.prevent="editingId = ''"
                />
              </form>
              <button v-else type="button" @click="openSession(session.session_id)">
                <strong>{{ session.title || "未命名会话" }}</strong>
                <span>{{ formatUpdatedAt(session.updated_at) }}</span>
              </button>
            </div>
            <span v-if="session.archived_at" class="conversation-history-status">已归档</span>
            <div class="conversation-history-actions">
              <button type="button" @click="openSession(session.session_id)">继续</button>
              <button type="button" @click="startRename(session)">重命名</button>
              <button
                type="button"
                @click="toggleArchive(session)"
              >
                {{ session.archived_at ? "恢复" : "归档" }}
              </button>
              <button class="danger-action" type="button" @click="removeSession(session)">
                删除
              </button>
            </div>
          </article>
        </div>
      </section>
    </div>
  </section>
</template>
