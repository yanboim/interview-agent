<script setup lang="ts">
// 管理端埋点分析分区：产品事件统计与趋势展示。
import { computed } from "vue";
import { useAdminStore } from "@/stores/admin";

const store = useAdminStore();
const counts = computed(() => {
  const result: Record<string, number> = {};
  for (const event of store.productEvents) {
    result[event.event_name] = (result[event.event_name] || 0) + 1;
  }
  return result;
});
const uniqueUsers = computed(
  () => new Set(store.productEvents.map((event) => event.user_id)).size,
);
const errorCount = computed(
  () =>
    (counts.value["client.error"] || 0)
    + (counts.value["client.unhandled_rejection"] || 0),
);
const funnel = computed(() => [
  { label: "设置目标", value: counts.value["profile.goal_saved"] || 0 },
  { label: "开始面试", value: counts.value["interview.started"] || 0 },
  { label: "完成面试", value: counts.value["interview.completed"] || 0 },
  { label: "生成计划", value: counts.value["learning.plan_generated"] || 0 },
]);
</script>

<template>
  <section class="admin-section">
    <div v-if="store.analyticsLoading" class="loading-state">正在加载产品数据…</div>
    <template v-else>
      <div class="count-grid">
        <article class="count-card"><span>事件数</span><strong>{{ store.productEvents.length }}</strong></article>
        <article class="count-card"><span>活跃用户</span><strong>{{ uniqueUsers }}</strong></article>
        <article class="count-card"><span>前端错误</span><strong>{{ errorCount }}</strong></article>
      </div>
      <article class="panel">
        <div class="panel-heading">
          <div><h2>核心漏斗</h2><p>最近 {{ store.productEvents.length }} 条事件</p></div>
        </div>
        <div class="analytics-funnel">
          <div v-for="item in funnel" :key="item.label">
            <span>{{ item.label }}</span><strong>{{ item.value }}</strong>
          </div>
        </div>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><h2>事件分布</h2><p>包含 Web Vitals 与客户端异常</p></div></div>
        <div class="analytics-events">
          <div v-for="([name, value]) in Object.entries(counts)" :key="name">
            <code>{{ name }}</code><strong>{{ value }}</strong>
          </div>
          <p v-if="!Object.keys(counts).length">暂无产品事件。</p>
        </div>
      </article>
    </template>
  </section>
</template>
