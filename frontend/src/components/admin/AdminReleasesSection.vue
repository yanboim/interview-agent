<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { formatDateTime } from "@/lib/format";
import { handleDialogKeydown } from "@/lib/focusTrap";
import { useAdminStore } from "@/stores/admin";
import type {
  DeploymentRelease,
  DeploymentReleaseStatus,
} from "@/types";

const admin = useAdminStore();
const search = ref("");
const environment = ref<"" | "production" | "canary">("");
const status = ref<"" | DeploymentReleaseStatus>("");
const selected = ref<DeploymentRelease | null>(null);
const drawer = ref<HTMLElement | null>(null);
const closeButton = ref<HTMLButtonElement | null>(null);
let trigger: HTMLElement | null = null;

const statusLabels: Record<DeploymentReleaseStatus, string> = {
  deploying: "部署中",
  succeeded: "发布成功",
  failed: "发布失败",
  rolled_back: "已回滚",
};

const filteredReleases = computed(() => {
  const query = search.value.trim().toLowerCase();
  return admin.releases.filter((release) => {
    if (environment.value && release.environment !== environment.value) return false;
    if (status.value && release.status !== status.value) return false;
    if (!query) return true;
    return [
      release.version,
      release.title,
      release.summary,
      release.commit_sha || "",
      ...release.changes,
    ].some((value) => value.toLowerCase().includes(query));
  });
});

const verificationEntries = computed(() =>
  selected.value ? Object.entries(selected.value.verification) : [],
);

function openDetails(release: DeploymentRelease, event: Event) {
  trigger = event.currentTarget as HTMLElement;
  selected.value = release;
  document.body.classList.add("drawer-open");
  nextTick(() => closeButton.value?.focus());
}

function closeDetails() {
  selected.value = null;
  document.body.classList.remove("drawer-open");
  nextTick(() => trigger?.focus());
}

function onDrawerKeydown(event: KeyboardEvent) {
  handleDialogKeydown(event, drawer.value, closeDetails);
}

function shortDigest(value: string | null) {
  if (!value) return "—";
  return value.startsWith("sha256:") ? value.slice(7, 19) : value.slice(0, 12);
}

watch(selected, (value) => {
  if (!value) document.body.classList.remove("drawer-open");
});
onBeforeUnmount(() => document.body.classList.remove("drawer-open"));
</script>

<template>
  <section class="admin-section release-center">
    <article class="panel release-intro">
      <div>
        <p class="eyebrow">Deployment ledger</p>
        <h2>最近发版记录</h2>
        <p>仅记录实际执行过的部署及其验证结果，Git 提交本身不会被视为已经上线。</p>
      </div>
      <button
        class="admin-icon-button"
        type="button"
        :disabled="admin.releasesLoading"
        @click="admin.loadReleases()"
      >
        <i class="ph ph-arrow-clockwise" aria-hidden="true"></i>
        {{ admin.releasesLoading ? "刷新中…" : "刷新记录" }}
      </button>
    </article>

    <div class="toolbar-row release-toolbar">
      <input
        v-model="search"
        class="search-input"
        type="search"
        placeholder="搜索版本、标题或变更…"
        aria-label="搜索发版记录"
      />
      <select v-model="environment" class="status-select" aria-label="按环境筛选">
        <option value="">全部环境</option>
        <option value="production">生产环境</option>
        <option value="canary">Canary</option>
      </select>
      <select v-model="status" class="status-select" aria-label="按发布状态筛选">
        <option value="">全部状态</option>
        <option value="succeeded">发布成功</option>
        <option value="deploying">部署中</option>
        <option value="failed">发布失败</option>
        <option value="rolled_back">已回滚</option>
      </select>
      <span class="toolbar-count">{{ filteredReleases.length }} 条</span>
    </div>

    <div v-if="admin.releasesLoading && !admin.releases.length" class="release-skeletons" aria-label="正在加载发版记录">
      <div v-for="index in 3" :key="index" class="release-skeleton skeleton"></div>
    </div>

    <div v-else-if="filteredReleases.length" class="release-timeline">
      <article
        v-for="release in filteredReleases"
        :key="release.release_id"
        class="release-card"
        :class="`is-${release.status}`"
      >
        <span class="release-marker" aria-hidden="true"></span>
        <div class="release-card-heading">
          <div>
            <div class="release-status-line">
              <span class="release-status" :class="`is-${release.status}`">
                {{ statusLabels[release.status] }}
              </span>
              <span>{{ release.environment === "production" ? "生产环境" : "Canary" }}</span>
            </div>
            <h3>{{ release.title }}</h3>
          </div>
          <time :datetime="release.started_at">{{ formatDateTime(release.started_at) }}</time>
        </div>
        <p v-if="release.summary" class="release-summary">{{ release.summary }}</p>
        <ul v-if="release.changes.length" class="release-change-preview">
          <li v-for="change in release.changes.slice(0, 3)" :key="change">{{ change }}</li>
        </ul>
        <div class="release-card-footer">
          <div class="release-meta">
            <span>版本 <strong>{{ release.version }}</strong></span>
            <span v-if="release.commit_sha">Commit <code>{{ shortDigest(release.commit_sha) }}</code></span>
            <span>触发者 {{ release.triggered_by }}</span>
          </div>
          <button
            class="release-detail-button"
            type="button"
            :aria-label="`查看 ${release.version} 发版详情`"
            @click="openDetails(release, $event)"
          >
            查看详情
            <i class="ph ph-arrow-right" aria-hidden="true"></i>
          </button>
        </div>
      </article>
    </div>

    <article v-else class="panel release-empty">
      <span class="release-empty-icon" aria-hidden="true">
        <i class="ph ph-rocket-launch"></i>
      </span>
      <h3>{{ admin.releases.length ? "没有匹配的发版记录" : "暂无发版记录" }}</h3>
      <p>
        {{ admin.releases.length
          ? "调整搜索词或筛选条件后再试。"
          : "下一次部署完成验证后，系统会自动在这里生成记录。" }}
      </p>
    </article>

    <Teleport to="body">
      <div
        v-if="selected"
        class="release-drawer-backdrop"
        @mousedown.self="closeDetails"
      >
        <aside
          ref="drawer"
          class="release-drawer"
          role="dialog"
          aria-modal="true"
          aria-labelledby="release-drawer-title"
          @keydown="onDrawerKeydown"
        >
          <header>
            <div>
              <p class="eyebrow">发布详情</p>
              <h2 id="release-drawer-title">{{ selected.title }}</h2>
            </div>
            <button
              ref="closeButton"
              class="drawer-close"
              type="button"
              aria-label="关闭发版详情"
              @click="closeDetails"
            >
              <i class="ph ph-x" aria-hidden="true"></i>
            </button>
          </header>

          <div class="release-drawer-body">
            <div class="release-detail-summary">
              <span class="release-status" :class="`is-${selected.status}`">
                {{ statusLabels[selected.status] }}
              </span>
              <span>{{ selected.environment === "production" ? "生产环境" : "Canary" }}</span>
              <span>{{ formatDateTime(selected.completed_at || selected.started_at) }}</span>
            </div>

            <section>
              <h3>基本信息</h3>
              <dl class="release-detail-list">
                <div><dt>版本</dt><dd>{{ selected.version }}</dd></div>
                <div><dt>触发者</dt><dd>{{ selected.triggered_by }}</dd></div>
                <div v-if="selected.commit_sha"><dt>Commit</dt><dd><code>{{ selected.commit_sha }}</code></dd></div>
                <div><dt>发布 ID</dt><dd><code>{{ selected.release_id }}</code></dd></div>
              </dl>
            </section>

            <section v-if="selected.summary || selected.changes.length">
              <h3>本次变更</h3>
              <p v-if="selected.summary">{{ selected.summary }}</p>
              <ul v-if="selected.changes.length">
                <li v-for="change in selected.changes" :key="change">{{ change }}</li>
              </ul>
            </section>

            <section>
              <h3>验证结果</h3>
              <div v-if="verificationEntries.length" class="release-verification">
                <div v-for="[name, result] in verificationEntries" :key="name">
                  <i class="ph ph-check-circle" aria-hidden="true"></i>
                  <span>{{ name }}</span>
                  <strong>{{ result }}</strong>
                </div>
              </div>
              <p v-else class="release-muted">未附加结构化验证结果。</p>
            </section>

            <details class="release-technical">
              <summary>技术信息</summary>
              <dl class="release-detail-list">
                <div><dt>应用镜像</dt><dd><code>{{ selected.app_image || "—" }}</code></dd></div>
                <div><dt>Worker 镜像</dt><dd><code>{{ selected.worker_image || "—" }}</code></dd></div>
                <div><dt>数据库版本</dt><dd><code>{{ selected.migration_revision || "—" }}</code></dd></div>
                <div><dt>恢复点</dt><dd><code>{{ selected.recovery_point || "—" }}</code></dd></div>
              </dl>
            </details>
          </div>
        </aside>
      </div>
    </Teleport>
  </section>
</template>
