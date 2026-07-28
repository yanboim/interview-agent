<script setup lang="ts">
import { computed } from "vue";
import { useAdminStore } from "@/stores/admin";
import {
  resourceExposureLabel,
  resourceStatusLabel,
} from "@/lib/adminResources";

const admin = useAdminStore();

const checkedAt = computed(() => {
  if (!admin.resourceCenter?.checked_at) return "尚未检查";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(admin.resourceCenter.checked_at));
});

const summaryItems = computed(() => {
  const summary = admin.resourceCenter?.summary;
  if (!summary) return [];
  return [
    ["正常", summary.healthy],
    ["异常", summary.unavailable],
    ["未探测", summary.unknown],
    ["未启用", summary.disabled],
  ] as const;
});
</script>

<template>
  <section class="admin-section resource-center">
    <article class="panel resource-center-intro">
      <div>
        <p class="eyebrow">Control plane</p>
        <h2>系统资源中心</h2>
        <p>
          统一查看服务状态和网络暴露边界。这里只展示脱敏摘要，不提供数据库连接串、凭据或底层管理入口。
        </p>
      </div>
      <button
        class="admin-icon-button"
        type="button"
        :disabled="admin.resourcesLoading"
        @click="admin.loadResources()"
      >
        <i class="ph ph-arrow-clockwise" aria-hidden="true"></i>
        {{ admin.resourcesLoading ? "检查中…" : "刷新状态" }}
      </button>
    </article>

    <div v-if="admin.resourcesLoading && !admin.resourceCenter" class="list-state skeleton">
      正在检查系统资源…
    </div>

    <template v-else-if="admin.resourceCenter">
      <div class="resource-summary">
        <article class="resource-overall">
          <span>整体状态</span>
          <strong :class="{ degraded: admin.resourceCenter.overall_status !== 'healthy' }">
            {{ admin.resourceCenter.overall_status === "healthy" ? "运行正常" : "需要关注" }}
          </strong>
          <small>检查时间：{{ checkedAt }}</small>
        </article>
        <article v-for="[label, value] in summaryItems" :key="label">
          <span>{{ label }}</span>
          <strong>{{ value }}</strong>
        </article>
      </div>

      <div class="resource-grid">
        <article
          v-for="resource in admin.resourceCenter.resources"
          :key="resource.id"
          class="resource-card"
        >
          <div class="resource-card-heading">
            <div>
              <p class="eyebrow">{{ resource.category }}</p>
              <h3>{{ resource.name }}</h3>
            </div>
            <span class="resource-status" :class="`is-${resource.status}`">
              {{ resourceStatusLabel(resource.status) }}
            </span>
          </div>

          <p class="resource-description">{{ resource.description }}</p>
          <p class="resource-detail">{{ resource.detail }}</p>

          <div class="resource-meta">
            <span>{{ resourceExposureLabel(resource.exposure) }}</span>
            <span>{{ resource.critical ? "关键依赖" : "辅助资源" }}</span>
            <span v-if="resource.latency_ms !== null">{{ resource.latency_ms }} ms</span>
          </div>

          <footer>
            <code>{{ resource.runbook }}</code>
            <a
              v-if="resource.console_url"
              :href="resource.console_url"
              target="_blank"
              rel="noopener noreferrer"
            >
              打开受控控制台
              <i class="ph ph-arrow-square-out" aria-hidden="true"></i>
            </a>
            <span v-else>无公开控制台入口</span>
          </footer>
        </article>
      </div>
    </template>
  </section>
</template>
