<script setup lang="ts">
// 管理后台主视图：概览/用户/审计/交互/知识/资源/发版等分区。
import { computed, onMounted, ref, watch } from "vue";
import { useToastStore } from "@/stores/toast";
import { useAdminStore } from "@/stores/admin";
import { useAdminAuthStore } from "@/stores/adminAuth";
import AdminOverviewSection from "@/components/admin/AdminOverviewSection.vue";
import AdminKnowledgeSection from "@/components/admin/AdminKnowledgeSection.vue";
import AdminUsersSection from "@/components/admin/AdminUsersSection.vue";
import AdminAuditsSection from "@/components/admin/AdminAuditsSection.vue";
import AdminAnalyticsSection from "@/components/admin/AdminAnalyticsSection.vue";
import AdminResourcesSection from "@/components/admin/AdminResourcesSection.vue";
import AdminReleasesSection from "@/components/admin/AdminReleasesSection.vue";

const toast = useToastStore();
const admin = useAdminStore();
const adminAuth = useAdminAuthStore();

const section = ref<
  "overview" | "resources" | "releases" | "analytics" | "knowledge" | "users" | "audits"
>("overview");
const loginError = ref("");
const loginUsername = ref("");
const loginPassword = ref("");
const loginSubmitting = ref(false);

const titles: Record<typeof section.value, string> = {
  overview: "运行概览",
  resources: "系统资源",
  releases: "发版记录",
  analytics: "产品分析",
  knowledge: "知识库",
  users: "用户管理",
  audits: "审计中心",
};

const isReady = computed(() => adminAuth.isAuthenticated && !adminAuth.initializing);
const operatorLinks = computed(() => admin.runtime?.operator_links ?? []);

async function submitLogin() {
  loginError.value = "";
  loginSubmitting.value = true;
  try {
    await adminAuth.login(loginUsername.value, loginPassword.value);
    await showSection("overview");
  } catch (e) {
    loginError.value = e instanceof Error ? e.message : "登录失败";
  } finally {
    loginSubmitting.value = false;
  }
}

async function showSection(name: typeof section.value) {
  section.value = name;
  try {
    if (name === "overview") await admin.loadOverview();
    if (name === "resources") await admin.loadResources();
    if (name === "releases") await admin.loadReleases();
    if (name === "analytics") await admin.loadAnalytics();
    if (name === "knowledge") await admin.loadKnowledge();
    if (name === "users") await admin.loadUsers();
    if (name === "audits") await admin.loadAudits();
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "加载失败", "error");
  }
}

async function doLogout() {
  await adminAuth.logout();
}

watch(section, (s) => showSection(s));

onMounted(async () => {
  await adminAuth.initialize();
  if (adminAuth.isAuthenticated) await showSection("overview");
});
</script>

<template>
  <!-- 未登录:登录卡 -->
  <div v-if="!isReady" class="login-overlay">
    <form class="login-card" @submit.prevent="submitLogin">
      <span class="brand-mark large" aria-hidden="true">IL</span>
      <p class="eyebrow">管理员访问</p>
      <h2>登录管理后台</h2>
      <p>仅管理员账号可以访问运行数据和知识库管理。</p>
      <label>
        用户名
        <input v-model="loginUsername" autocomplete="username" required :disabled="loginSubmitting" />
      </label>
      <label>
        密码
        <input
          v-model="loginPassword"
          type="password"
          autocomplete="current-password"
          required
          :disabled="loginSubmitting"
        />
      </label>
      <div v-if="loginError" class="form-error">{{ loginError }}</div>
      <button class="primary-button" type="submit" :disabled="loginSubmitting">
        {{ loginSubmitting ? "登录中…" : "登录后台" }}
      </button>
    </form>
  </div>

  <!-- 已登录:后台主体 -->
  <div v-else class="admin-shell">
    <aside class="admin-sidebar">
      <a class="admin-brand" href="/" aria-label="返回 Interview Lab">
        <span class="brand-mark" aria-hidden="true">IL</span>
        <span><strong>Interview Lab</strong><small>管理控制台</small></span>
      </a>
      <nav aria-label="后台导航">
        <button
          v-for="key in (['overview', 'resources', 'releases', 'analytics', 'knowledge', 'users', 'audits'] as const)"
          :key="key"
          class="nav-button"
          :class="{ active: section === key }"
          type="button"
          @click="section = key"
        >
          {{ titles[key] }}
        </button>
        <div v-if="operatorLinks.length" class="operator-link-group">
          <span class="nav-group-label">运维工具</span>
          <a
            v-for="link in operatorLinks"
            :key="link.id"
            class="nav-button operator-link"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            <i
              :class="link.id === 'grafana' ? 'ph ph-chart-line-up' : 'ph ph-activity'"
              aria-hidden="true"
            ></i>
            {{ link.name }}
            <i class="ph ph-arrow-square-out external-link-icon" aria-hidden="true"></i>
          </a>
        </div>
      </nav>
      <div class="sidebar-bottom">
        <a href="/" class="back-link">
          <i class="ph ph-arrow-left" aria-hidden="true"></i>
          返回面试教练
        </a>
        <button class="ghost-button" type="button" @click="doLogout">
          <i class="ph ph-sign-out" aria-hidden="true"></i>
          退出登录
        </button>
      </div>
    </aside>

    <main class="admin-main">
      <header class="admin-header">
        <div>
          <p class="eyebrow">管理控制台</p>
          <h1>{{ titles[section] }}</h1>
        </div>
        <div class="operator">
          <i class="ph ph-user-circle operator-icon" aria-hidden="true"></i>
          <span>{{ adminAuth.username || "管理员" }}</span>
        </div>
      </header>

      <AdminOverviewSection v-show="section === 'overview'" />
      <AdminResourcesSection v-show="section === 'resources'" />
      <AdminReleasesSection v-show="section === 'releases'" />
      <AdminAnalyticsSection v-show="section === 'analytics'" />
      <AdminKnowledgeSection v-show="section === 'knowledge'" />
      <AdminUsersSection v-show="section === 'users'" />
      <AdminAuditsSection v-show="section === 'audits'" />
    </main>
  </div>
</template>

<style src="@/styles/admin.css"></style>
