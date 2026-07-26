<script setup lang="ts">
import { computed, ref, watch } from "vue";
import Pagination from "@/components/Pagination.vue";
import { formatDateTime } from "@/lib/format";
import { useAdminStore } from "@/stores/admin";

const PAGE_SIZE = 10;
const admin = useAdminStore();
const search = ref("");
const status = ref<"" | "success" | "error" | "denied">("");
const page = ref(1);

const filteredAudits = computed(() => {
  const query = search.value.trim().toLowerCase();
  return admin.audits.filter((audit) => {
    if (status.value && audit.status !== status.value) return false;
    if (!query) return true;
    return (
      audit.tool_name.toLowerCase().includes(query)
      || audit.user_id.toLowerCase().includes(query)
      || audit.input_summary.toLowerCase().includes(query)
    );
  });
});
const totalPages = computed(() => Math.max(1, Math.ceil(filteredAudits.value.length / PAGE_SIZE)));
const pagedAudits = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return filteredAudits.value.slice(start, start + PAGE_SIZE);
});

watch([search, status], () => (page.value = 1));
</script>

<template>
  <section class="admin-section">
    <article class="panel">
      <div class="panel-heading">
        <div><p class="eyebrow">审计日志</p><h2>最近工具调用</h2></div>
        <button class="admin-icon-button" type="button" :disabled="admin.auditsLoading" aria-label="刷新审计列表" @click="admin.loadAudits()">
          <i class="ph ph-arrow-clockwise" aria-hidden="true"></i>
        </button>
      </div>
      <div class="toolbar-row">
        <input v-model="search" class="search-input" type="search" placeholder="搜索工具、用户或输入…" aria-label="搜索审计" />
        <select v-model="status" class="status-select" aria-label="按状态筛选">
          <option value="">全部状态</option>
          <option value="success">成功</option>
          <option value="error">错误</option>
          <option value="denied">拒绝</option>
        </select>
        <span class="toolbar-count">{{ filteredAudits.length }} / {{ admin.audits.length }} 条</span>
      </div>
      <div v-if="admin.auditsLoading" class="list-state skeleton">正在加载审计…</div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>时间</th><th>用户</th><th>工具</th><th>状态</th><th>耗时</th><th>输入摘要</th></tr></thead>
          <tbody>
            <tr v-for="row in pagedAudits" :key="row.audit_id">
              <td>{{ formatDateTime(row.created_at) }}</td>
              <td>{{ row.user_id }}</td>
              <td>{{ row.tool_name }}</td>
              <td :class="`audit-${row.status}`">{{ row.status }}</td>
              <td>{{ row.duration_ms }} ms</td>
              <td>{{ row.input_summary }}</td>
            </tr>
            <tr v-if="!pagedAudits.length"><td colspan="6">没有匹配的审计记录</td></tr>
          </tbody>
        </table>
      </div>
      <Pagination v-if="totalPages > 1" v-model:page="page" :total-pages="totalPages" />
    </article>
  </section>
</template>
