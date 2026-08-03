<script setup lang="ts">
// 管理端审计分区：审计事件、工具审计与交互追踪查询。
import { computed, ref, watch } from "vue";
import Pagination from "@/components/Pagination.vue";
import { formatDateTime } from "@/lib/format";
import { useAdminStore } from "@/stores/admin";
import type { AdminInteraction } from "@/types";

const PAGE_SIZE = 12;
const admin = useAdminStore();
const tab = ref<"activity" | "interactions">("activity");
const search = ref("");
const outcome = ref<"" | "success" | "error" | "denied">("");
const interactionType = ref<"" | "chat" | "interview">("");
const page = ref(1);
const selected = ref<AdminInteraction | null>(null);

const filteredActivity = computed(() => {
  const query = search.value.trim().toLowerCase();
  return admin.auditEvents.filter((event) => {
    if (outcome.value && event.outcome !== outcome.value) return false;
    if (!query) return true;
    return [
      event.actor_username,
      event.actor_user_id,
      event.action,
      event.resource_type,
      event.resource_id,
      event.request_id,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  });
});

const filteredInteractions = computed(() => {
  const query = search.value.trim().toLowerCase();
  return admin.interactions.filter((interaction) => {
    if (
      interactionType.value
      && interaction.interaction_type !== interactionType.value
    ) return false;
    if (!query) return true;
    return [
      interaction.username,
      interaction.user_id,
      interaction.container_title,
      interaction.input_text,
      interaction.output_text,
    ].some((value) => value.toLowerCase().includes(query));
  });
});

const activeRows = computed(() => (
  tab.value === "activity"
    ? filteredActivity.value
    : filteredInteractions.value
));
const totalPages = computed(
  () => Math.max(1, Math.ceil(activeRows.value.length / PAGE_SIZE)),
);
const pagedActivity = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return filteredActivity.value.slice(start, start + PAGE_SIZE);
});
const pagedInteractions = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return filteredInteractions.value.slice(start, start + PAGE_SIZE);
});

function prettyJson(value: string): string {
  try {
    return JSON.stringify(JSON.parse(value || "{}"), null, 2);
  } catch {
    return value;
  }
}

async function inspect(interaction: AdminInteraction) {
  selected.value = interaction;
  await admin.loadInteractionTrace(interaction);
}

watch([search, outcome, interactionType, tab], () => {
  page.value = 1;
  selected.value = null;
});
</script>

<template>
  <section class="admin-section audit-center">
    <article class="panel">
      <div class="panel-heading audit-heading">
        <div>
          <p class="eyebrow">可观测性与审计</p>
          <h2>用户活动与交互记录</h2>
          <p>内容读取同样会写入操作审计；敏感凭据不会在此展示。</p>
        </div>
        <button
          class="admin-icon-button"
          type="button"
          :disabled="admin.auditsLoading"
          aria-label="刷新审计中心"
          @click="admin.loadAudits()"
        >
          <i class="ph ph-arrow-clockwise" aria-hidden="true"></i>
        </button>
      </div>

      <div class="audit-tabs" role="tablist" aria-label="审计视图">
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'activity'"
          :class="{ active: tab === 'activity' }"
          @click="tab = 'activity'"
        >
          操作审计
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'interactions'"
          :class="{ active: tab === 'interactions' }"
          @click="tab = 'interactions'"
        >
          交互记录与执行链路
        </button>
      </div>

      <div class="toolbar-row">
        <input
          v-model="search"
          class="search-input"
          type="search"
          placeholder="搜索用户、动作、内容或 Request ID…"
          aria-label="搜索审计中心"
        />
        <select
          v-if="tab === 'activity'"
          v-model="outcome"
          class="status-select"
          aria-label="按结果筛选"
        >
          <option value="">全部结果</option>
          <option value="success">成功</option>
          <option value="error">错误</option>
          <option value="denied">拒绝</option>
        </select>
        <select
          v-else
          v-model="interactionType"
          class="status-select"
          aria-label="按交互类型筛选"
        >
          <option value="">全部交互</option>
          <option value="chat">聊天</option>
          <option value="interview">面试</option>
        </select>
        <span class="toolbar-count">{{ activeRows.length }} 条</span>
      </div>

      <div v-if="admin.auditsLoading" class="list-state skeleton">
        正在加载审计与交互记录…
      </div>

      <div v-else-if="tab === 'activity'" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th><th>用户</th><th>动作</th><th>目标</th>
              <th>结果</th><th>耗时</th><th>Request ID</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in pagedActivity" :key="row.event_id">
              <td>{{ formatDateTime(row.created_at) }}</td>
              <td>
                {{ row.actor_username || "未认证" }}
                <small>{{ row.actor_user_id || "—" }}</small>
              </td>
              <td><code>{{ row.action }}</code></td>
              <td>{{ row.resource_type }} · {{ row.resource_id || "—" }}</td>
              <td :class="`audit-${row.outcome}`">{{ row.outcome }}</td>
              <td>{{ row.duration_ms }} ms</td>
              <td><code>{{ row.request_id }}</code></td>
            </tr>
            <tr v-if="!pagedActivity.length">
              <td colspan="7">没有匹配的操作审计。</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="interaction-list">
        <button
          v-for="row in pagedInteractions"
          :key="`${row.interaction_type}:${row.interaction_id}`"
          class="interaction-row"
          type="button"
          @click="inspect(row)"
        >
          <span class="interaction-meta">
            <strong>{{ row.username }}</strong>
            <span>{{ row.interaction_type === "chat" ? "聊天" : "面试" }}</span>
            <span>{{ formatDateTime(row.created_at) }}</span>
            <span :class="`audit-${row.status === 'completed' ? 'success' : 'error'}`">
              {{ row.status }}
            </span>
          </span>
          <span class="interaction-title">{{ row.container_title }}</span>
          <span class="interaction-preview">{{ row.input_text }}</span>
        </button>
        <p v-if="!pagedInteractions.length" class="list-state">
          没有匹配的交互记录。
        </p>
      </div>

      <Pagination
        v-if="totalPages > 1"
        v-model:page="page"
        :total-pages="totalPages"
      />
    </article>

    <article v-if="selected" class="panel interaction-detail">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">权威业务记录</p>
          <h2>{{ selected.username }} · {{ selected.container_title }}</h2>
          <p><code>{{ selected.interaction_id }}</code></p>
        </div>
        <button type="button" class="text-action" @click="selected = null">
          关闭
        </button>
      </div>
      <div v-if="selected.prompt_text" class="content-block">
        <strong>系统问题</strong>
        <pre>{{ selected.prompt_text }}</pre>
      </div>
      <div class="content-block">
        <strong>用户输入</strong>
        <pre>{{ selected.input_text }}</pre>
      </div>
      <div class="content-block">
        <strong>系统输出</strong>
        <pre>{{ selected.output_text || "尚无最终输出" }}</pre>
      </div>
      <div v-if="selected.error" class="content-block error">
        <strong>失败信息</strong>
        <pre>{{ selected.error }}</pre>
      </div>

      <div class="trace-heading">
        <p class="eyebrow">执行追踪</p>
        <h3>Request → Agent/评估 → 工具 → 结果</h3>
      </div>
      <div v-if="admin.traceLoading" class="list-state skeleton">
        正在读取执行链路…
      </div>
      <ol v-else class="trace-list">
        <li v-for="trace in admin.executionTrace" :key="trace.trace_id">
          <span class="trace-marker"></span>
          <div>
            <strong>{{ trace.stage }}</strong>
            <span>{{ trace.status }} · {{ trace.duration_ms ?? "—" }} ms</span>
            <time>{{ formatDateTime(trace.created_at) }}</time>
            <code>{{ trace.request_id }}</code>
            <pre>{{ prettyJson(trace.detail_json) }}</pre>
          </div>
        </li>
        <li v-if="!admin.executionTrace.length" class="list-state">
          该历史交互尚无执行追踪；新交互会自动记录。
        </li>
      </ol>
    </article>
  </section>
</template>
