<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, toRaw, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { exportResumeDocx } from "@/api/resumes";
import { confirm } from "@/composables/confirm";
import { useAuthStore } from "@/stores/auth";
import { useResumesStore } from "@/stores/resumes";
import { useToastStore } from "@/stores/toast";
import type { ResumeDraft } from "@/types";
import UiButton from "@/components/ui/UiButton.vue";
import UiState from "@/components/ui/UiState.vue";

const auth = useAuthStore();
const store = useResumesStore();
const toast = useToastStore();
const route = useRoute();
const router = useRouter();

const file = ref<File | null>(null);
const jobDescription = ref(auth.interviewGoal?.jobDescription || "");
const draft = ref<ResumeDraft | null>(null);
const saving = ref(false);
const downloading = ref(false);
let pollTimer: number | undefined;

const analysis = computed(() => store.activeAnalysis);
const processing = computed(() =>
  ["uploaded", "pending", "processing"].includes(
    analysis.value?.status || store.active?.status || "",
  ),
);
const canExport = computed(
  () =>
    analysis.value?.status === "ready"
    && !analysis.value.warnings.length
    && !(draft.value?.pending_questions.length),
);
const scoreLabels: Record<string, string> = {
  match: "岗位匹配",
  completeness: "内容完整",
  relevance: "内容相关",
  clarity: "表达清晰",
  impact: "成果影响",
  ats: "ATS可读",
};
const statusLabels: Record<string, string> = {
  uploaded: "已上传",
  pending: "等待评估",
  processing: "评估中",
  ready: "已完成",
  failed: "评估失败",
};
const severityLabels: Record<string, string> = {
  high: "高优先级",
  medium: "中优先级",
  low: "低优先级",
};

function statusLabel(status: string) {
  return statusLabels[status] || status;
}

function severityLabel(severity: string) {
  return severityLabels[severity] || severity;
}

function scoreWidth(score: number) {
  return `${Math.max(0, Math.min(100, score))}%`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatFileSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MiB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KiB`;
}

watch(
  () => `${analysis.value?.analysis_id || ""}:${analysis.value?.revision || 0}`,
  () => {
    draft.value = analysis.value?.draft
      ? structuredClone(toRaw(analysis.value.draft))
      : null;
  },
  { immediate: true },
);

watch(
  () => processing.value,
  (active) => {
    window.clearInterval(pollTimer);
    if (active && store.active) {
      pollTimer = window.setInterval(
        () => store.open(store.active!.resume_id),
        3000,
      );
    }
  },
  { immediate: true },
);

function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] || null;
}

async function upload() {
  if (!file.value) return;
  try {
    const created = await store.upload(file.value, jobDescription.value);
    await router.push(`/resumes/${encodeURIComponent(created.resume_id)}`);
    toast.show("简历已上传，正在评估", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "简历上传失败", "error");
  }
}

async function openResume(resumeId: string) {
  await router.push(`/resumes/${encodeURIComponent(resumeId)}`);
  await store.open(resumeId);
}

async function reanalyze() {
  if (!store.active) return;
  try {
    await store.reanalyze(store.active.resume_id, jobDescription.value);
    toast.show("新的简历评估已提交", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "重新评估失败", "error");
  }
}

async function saveDraft() {
  if (!draft.value) return;
  saving.value = true;
  try {
    await store.saveDraft(draft.value);
    toast.show("优化稿已保存", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "保存失败", "error");
    if (store.active) await store.open(store.active.resume_id);
  } finally {
    saving.value = false;
  }
}

function removePending(index: number) {
  draft.value?.pending_questions.splice(index, 1);
}

async function download() {
  if (!analysis.value || !canExport.value) return;
  downloading.value = true;
  try {
    const result = await exportResumeDocx(analysis.value.analysis_id);
    const url = URL.createObjectURL(result.blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = result.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "导出失败", "error");
  } finally {
    downloading.value = false;
  }
}

async function removeResume() {
  if (!store.active) return;
  const approved = await confirm({
    title: "删除简历？",
    message: "原件和全部评估版本将被删除，历史模拟面试不会自动删除。",
    detail: store.active.original_filename,
    confirmText: "删除",
    danger: true,
  });
  if (!approved) return;
  await store.remove(store.active.resume_id);
  await router.push("/resumes");
  toast.show("简历已删除", "success");
}

onMounted(async () => {
  await store.load();
  const resumeId = route.params.resumeId;
  if (typeof resumeId === "string" && resumeId) await store.open(resumeId);
});

onUnmounted(() => window.clearInterval(pollTimer));
</script>

<template>
  <section class="resume-panel">
    <div class="resume-layout">
      <aside class="resume-sidebar" aria-label="简历列表">
        <header class="resume-sidebar-intro">
          <p class="eyebrow">RESUME CENTER</p>
          <h1>简历中心</h1>
          <p>评估岗位匹配度，整理证据并生成可信的优化稿。</p>
        </header>

        <form class="resume-upload-card" @submit.prevent="upload">
          <div class="resume-card-heading">
            <div>
              <h2>上传新简历</h2>
              <p>支持 PDF 或 DOCX，单个文件不超过 10 MB</p>
            </div>
            <span aria-hidden="true">01</span>
          </div>
          <label class="resume-field">
            <span>选择简历文件</span>
            <input
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              required
              @change="chooseFile"
            />
          </label>
          <label class="resume-field">
            <span>目标 JD（可选）</span>
            <textarea
              v-model="jobDescription"
              rows="4"
              maxlength="20000"
              placeholder="为空时使用个人目标中的JD或目标岗位"
            />
          </label>
          <p class="resume-privacy-note">
            <span aria-hidden="true"></span>
            简历正文会发送给已配置的模型用于本次评估，不会进入公共知识库。
          </p>
          <UiButton type="submit" :loading="store.loading" :disabled="!file">
            上传并评估
          </UiButton>
        </form>

        <section class="resume-history">
          <div class="resume-history-heading">
            <h2>我的简历</h2>
            <span>{{ store.items.length }}</span>
          </div>
          <UiState
            v-if="store.loading && !store.items.length"
            kind="loading"
            title="正在加载简历"
          />
          <UiState
            v-else-if="store.error"
            kind="error"
            title="简历加载失败"
            :detail="store.error"
          />
          <p v-else-if="!store.items.length" class="resume-history-empty">
            上传第一份简历后，可持续保存不同岗位的评估版本。
          </p>
          <div v-else class="resume-list">
            <button
              v-for="item in store.items"
              :key="item.resume_id"
              type="button"
              :class="{ active: item.resume_id === store.active?.resume_id }"
              @click="openResume(item.resume_id)"
            >
              <span class="resume-list-main">
                <strong>{{ item.original_filename }}</strong>
                <small>{{ formatDate(item.updated_at) }}</small>
              </span>
              <span
                class="resume-status"
                :class="`status-${item.latest_analysis?.status || item.status}`"
              >
                {{ statusLabel(item.latest_analysis?.status || item.status) }}
              </span>
            </button>
          </div>
        </section>
      </aside>

      <main class="resume-detail">
        <UiState
          v-if="!store.active"
          title="选择一份简历"
          detail="这里会展示岗位匹配、问题证据、改写建议和完整优化稿。"
        />
        <template v-else>
          <header class="resume-detail-heading">
            <div>
              <p class="eyebrow">简历评估</p>
              <h1>{{ store.active.original_filename }}</h1>
              <div class="resume-meta">
                <span
                  class="resume-status"
                  :class="`status-${analysis?.status || store.active.status}`"
                >
                  {{ statusLabel(analysis?.status || store.active.status) }}
                </span>
                <span>{{ formatFileSize(store.active.size_bytes) }}</span>
                <span>更新于 {{ formatDate(store.active.updated_at) }}</span>
              </div>
            </div>
            <div class="resume-heading-actions">
              <UiButton variant="text" @click="reanalyze">使用当前JD重新评估</UiButton>
              <UiButton variant="danger" @click="removeResume">删除</UiButton>
            </div>
          </header>

          <UiState
            v-if="processing"
            kind="loading"
            title="正在解析和评估简历"
            detail="可以离开此页面，稍后返回会从服务端恢复进度。"
          />
          <UiState
            v-else-if="analysis?.status === 'failed'"
            kind="error"
            title="简历评估失败"
            :detail="analysis.error || store.active.error || '请检查文件后重新评估'"
          >
            <UiButton @click="reanalyze">重试评估</UiButton>
          </UiState>

          <template v-else-if="analysis?.status === 'ready' && analysis.report">
            <section class="resume-report-card">
              <div class="resume-section-title">
                <div>
                  <p class="eyebrow">ASSESSMENT</p>
                  <h2>简历竞争力</h2>
                </div>
                <span>{{ analysis.target_role || "目标岗位" }}</span>
              </div>
              <div class="resume-score-grid" aria-label="简历评分">
                <article v-for="(value, key) in analysis.report.scores" :key="key">
                  <header>
                    <span>{{ scoreLabels[key] || key }}</span>
                    <strong>{{ Math.round(value) }}</strong>
                  </header>
                  <div class="resume-score-track" aria-hidden="true">
                    <i :style="{ width: scoreWidth(value) }"></i>
                  </div>
                </article>
              </div>
            </section>

            <section class="resume-keywords">
              <article>
                <h3><span class="keyword-mark matched" aria-hidden="true"></span>已覆盖关键词</h3>
                <div class="resume-keyword-list">
                  <span v-for="item in analysis.report.keyword_matches" :key="item">{{ item }}</span>
                  <p v-if="!analysis.report.keyword_matches.length">暂无</p>
                </div>
              </article>
              <article>
                <h3><span class="keyword-mark gap" aria-hidden="true"></span>建议补强关键词</h3>
                <div class="resume-keyword-list gap">
                  <span v-for="item in analysis.report.keyword_gaps" :key="item">{{ item }}</span>
                  <p v-if="!analysis.report.keyword_gaps.length">暂无</p>
                </div>
              </article>
            </section>

            <section class="resume-issues">
              <div class="resume-section-title">
                <div>
                  <p class="eyebrow">EVIDENCE</p>
                  <h2>问题与证据</h2>
                </div>
                <span>{{ analysis.report.issues.length }} 项建议</span>
              </div>
              <article
                v-for="(issue, index) in analysis.report.issues"
                :key="`${issue.category}-${index}`"
                :class="`severity-${issue.severity}`"
              >
                <header>
                  <div>
                    <span class="resume-severity">{{ severityLabel(issue.severity) }}</span>
                    <span class="resume-category">{{ issue.category }}</span>
                  </div>
                  <strong>{{ issue.message }}</strong>
                </header>
                <div class="resume-issue-detail">
                  <div>
                    <h3>原文证据</h3>
                    <blockquote>{{ issue.evidence }}</blockquote>
                  </div>
                  <div>
                    <h3>优化建议</h3>
                    <p>{{ issue.suggestion }}</p>
                  </div>
                </div>
              </article>
            </section>

            <section v-if="draft" class="resume-editor">
              <div class="resume-section-heading">
                <div>
                  <p class="eyebrow">OPTIMIZED DRAFT</p>
                  <h3>完整优化稿</h3>
                  <p>修改后保存；系统会重新检查无来源数字和待补充项。</p>
                </div>
                <span class="resume-version">版本 {{ analysis.revision }}</span>
              </div>
              <div class="resume-editor-basics">
                <label>姓名<input v-model="draft.name" aria-label="姓名" maxlength="100" /></label>
                <label>目标标题<input v-model="draft.headline" aria-label="目标标题" maxlength="200" /></label>
              </div>
              <label>个人简介<textarea v-model="draft.summary" aria-label="个人简介" rows="5" /></label>
              <fieldset
                v-for="(section, sectionIndex) in draft.sections"
                :key="sectionIndex"
              >
                <legend><span>{{ String(sectionIndex + 1).padStart(2, "0") }}</span> 简历章节</legend>
                <label>章节标题<input v-model="section.title" :aria-label="`第 ${sectionIndex + 1} 章标题`" /></label>
                <label
                  v-for="(_item, itemIndex) in section.items"
                  :key="itemIndex"
                >
                  条目 {{ itemIndex + 1 }}
                  <textarea
                    v-model="section.items[itemIndex]"
                    :aria-label="`第 ${sectionIndex + 1} 章第 ${itemIndex + 1} 条内容`"
                    rows="3"
                  />
                </label>
              </fieldset>

              <div v-if="draft.pending_questions.length" class="resume-pending">
                <h4>待补充信息</h4>
                <div
                  v-for="(question, index) in draft.pending_questions"
                  :key="index"
                >
                  <input
                    v-model="draft.pending_questions[index]"
                    :aria-label="`待补充问题${index + 1}`"
                    :placeholder="question"
                  />
                  <button type="button" @click="removePending(index)">已处理</button>
                </div>
              </div>

              <div v-if="analysis.warnings.length" class="resume-warnings" role="alert">
                <strong>导出前需要处理</strong>
                <ul>
                  <li v-for="warning in analysis.warnings" :key="warning.message">
                    {{ warning.message }}
                  </li>
                </ul>
              </div>

              <div class="resume-editor-actions">
                <div>
                  <strong>保存后可导出 DOCX</strong>
                  <span v-if="!canExport">请先处理待补充项和内容警告</span>
                </div>
                <div>
                  <UiButton :loading="saving" @click="saveDraft">保存优化稿</UiButton>
                <UiButton
                  variant="text"
                  :loading="downloading"
                  :disabled="!canExport"
                  @click="download"
                >
                  导出 DOCX
                </UiButton>
                </div>
              </div>
            </section>
          </template>
        </template>
      </main>
    </div>
  </section>
</template>

<style src="@/styles/resume.css"></style>
