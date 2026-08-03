<script setup lang="ts">
// 管理端用户分区：用户列表与角色变更。
import { computed, ref, watch } from "vue";
import Pagination from "@/components/Pagination.vue";
import { formatDateTime } from "@/lib/format";
import { useAdminStore } from "@/stores/admin";

const PAGE_SIZE = 10;
const admin = useAdminStore();
const search = ref("");
const page = ref(1);

const filteredUsers = computed(() => {
  const query = search.value.trim().toLowerCase();
  const productUsers = admin.users.filter((user) => user.role === "user");
  if (!query) return productUsers;
  return productUsers.filter(
    (user) =>
      user.username.toLowerCase().includes(query)
      || user.user_id.toLowerCase().includes(query),
  );
});
const totalPages = computed(() => Math.max(1, Math.ceil(filteredUsers.value.length / PAGE_SIZE)));
const pagedUsers = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return filteredUsers.value.slice(start, start + PAGE_SIZE);
});

watch(search, () => (page.value = 1));
</script>

<template>
  <section class="admin-section">
    <article class="panel">
      <div class="panel-heading">
        <div><p class="eyebrow">产品运营</p><h2>产品用户</h2></div>
        <button class="admin-icon-button" type="button" :disabled="admin.usersLoading" aria-label="刷新用户列表" @click="admin.loadUsers()">
          <i class="ph ph-arrow-clockwise" aria-hidden="true"></i>
        </button>
      </div>
      <div class="toolbar-row">
        <input v-model="search" class="search-input" type="search" placeholder="搜索用户名或 ID…" aria-label="搜索用户" />
        <span class="toolbar-count">{{ filteredUsers.length }} 个产品用户</span>
      </div>
      <div v-if="admin.usersLoading" class="list-state skeleton">正在加载用户…</div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>用户</th><th>会话</th><th>面试</th><th>创建时间</th></tr></thead>
          <tbody>
            <tr v-for="user in pagedUsers" :key="user.user_id">
              <td><strong>{{ user.username }}</strong><small>{{ user.user_id }}</small></td>
              <td>{{ user.conversation_count }}</td>
              <td>{{ user.interview_count }}</td>
              <td>{{ formatDateTime(user.created_at) }}</td>
            </tr>
            <tr v-if="!pagedUsers.length"><td colspan="4">没有匹配的用户</td></tr>
          </tbody>
        </table>
      </div>
      <Pagination v-if="totalPages > 1" v-model:page="page" :total-pages="totalPages" />
    </article>
  </section>
</template>
