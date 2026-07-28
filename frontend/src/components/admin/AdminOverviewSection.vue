<script setup lang="ts">
import { useAdminStore } from "@/stores/admin";

const admin = useAdminStore();

const countLabels: Record<string, string> = {
  users: "用户",
  conversations: "会话",
  interviews: "模拟面试",
  learning_tasks: "学习任务",
  messages: "消息",
  tool_audit_logs: "工具调用",
  audit_events: "操作审计",
  execution_traces: "执行追踪",
  active_tokens: "有效令牌",
  interview_turns: "面试问答",
};
</script>

<template>
  <section class="admin-section">
    <div v-if="admin.overviewLoading" class="list-state skeleton">正在加载运行概览…</div>
    <template v-else-if="admin.summary && admin.runtime">
      <div class="count-grid">
        <article
          v-for="[key, value] in Object.entries(admin.summary.counts)"
          :key="key"
          class="count-card"
        >
          <span>{{ countLabels[key] || key }}</span>
          <strong>{{ value }}</strong>
        </article>
      </div>
      <div class="two-column">
        <article class="panel">
          <div class="panel-heading">
            <div><p class="eyebrow">基础设施</p><h2>依赖状态</h2></div>
            <button class="admin-icon-button" type="button" aria-label="刷新概览" @click="admin.loadOverview()">
              <i class="ph ph-arrow-clockwise" aria-hidden="true"></i>
            </button>
          </div>
          <div class="status-list">
            <div
              v-for="[name, item] in Object.entries(admin.runtime.dependencies)"
              :key="name"
              class="status-row"
            >
              <strong>{{ name }}</strong>
              <span class="status-meta">{{ item.detail }}</span>
              <span class="status-badge" :class="{ error: item.status !== 'ok' }">
                {{ item.status === "ok" ? "正常" : "异常" }}
              </span>
            </div>
          </div>
        </article>
        <article class="panel">
          <div class="panel-heading">
            <div><p class="eyebrow">功能开关</p><h2>功能状态</h2></div>
          </div>
          <div class="feature-grid">
            <div
              v-for="[name, enabled] in Object.entries(admin.runtime.features)"
              :key="name"
              class="feature"
            >
              <span>{{ name }}</span>
              <strong :class="{ off: !enabled }">{{ enabled ? "已启用" : "未启用" }}</strong>
            </div>
          </div>
        </article>
      </div>
      <article class="panel">
        <div class="panel-heading">
          <div><p class="eyebrow">多 Agent</p><h2>Agent 拓扑</h2></div>
          <span class="pill">{{ admin.runtime.agent.mode }}</span>
        </div>
        <div class="agent-grid">
          <article
            v-for="agent in admin.runtime.agent.specialists"
            :key="agent.name"
            class="agent-card"
          >
            <strong>{{ agent.name }}</strong>
            <p>{{ agent.responsibility }}</p>
          </article>
        </div>
      </article>
    </template>
  </section>
</template>
