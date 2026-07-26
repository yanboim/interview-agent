<script setup lang="ts">
import { computed, ref } from "vue";
import { confirm } from "@/composables/confirm";
import { formatDateTime, formatSize } from "@/lib/format";
import { useAdminStore } from "@/stores/admin";
import { useToastStore } from "@/stores/toast";

const admin = useAdminStore();
const toast = useToastStore();
const knowledgeFile = ref<File | null>(null);
const dragover = ref(false);
const importPolling = ref(false);
const search = ref("");

const filteredFiles = computed(() => {
  const query = search.value.trim().toLowerCase();
  return query
    ? admin.knowledgeFiles.filter((file) => file.filename.toLowerCase().includes(query))
    : admin.knowledgeFiles;
});

async function upload() {
  const file = knowledgeFile.value;
  if (!file) return toast.show("请先选择 .md 或 .txt 文件", "error");
  if (file.size > 1_000_000) return toast.show("文件不能超过 1 MB", "error");
  try {
    await admin.uploadFile(file.name, await file.text());
    knowledgeFile.value = null;
    toast.show("文件已保存,请执行后台导入", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "上传失败", "error");
  }
}

function onDrop(event: DragEvent) {
  dragover.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file) knowledgeFile.value = file;
}

async function remove(filename: string) {
  const accepted = await confirm({
    title: "删除知识文件？",
    message: "删除后需重新导入才能生效。",
    detail: filename,
    confirmText: "删除",
    danger: true,
  });
  if (!accepted) return;
  try {
    await admin.deleteFile(filename);
    toast.show("知识文件已删除", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "删除失败", "error");
  }
}

async function startImport() {
  try {
    await admin.startImport();
    importPolling.value = true;
    for (let attempt = 0; attempt < 120; attempt++) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      if (await admin.pollImport()) break;
    }
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "导入失败", "error");
  } finally {
    importPolling.value = false;
  }
}
</script>

<template>
  <section class="admin-section">
    <div class="two-column knowledge-layout">
      <article class="panel upload-panel">
        <div class="panel-heading">
          <div><p class="eyebrow">文档</p><h2>添加知识文件</h2></div>
        </div>
        <label
          class="file-drop"
          :class="{ dragover }"
          @dragover.prevent="dragover = true"
          @dragleave="dragover = false"
          @drop.prevent="onDrop"
        >
          <input
            type="file"
            accept=".md,.txt,text/plain,text/markdown"
            @change="knowledgeFile = ($event.target as HTMLInputElement).files?.[0] || null"
          />
          <strong>{{ knowledgeFile ? knowledgeFile.name : "选择 Markdown 或 TXT（可拖入）" }}</strong>
          <span>最大 1 MB,文件会持久化保存</span>
        </label>
        <button class="primary-button" type="button" :disabled="admin.knowledgeLoading" @click="upload">
          <i class="ph ph-floppy-disk" aria-hidden="true"></i>
          保存文件
        </button>
        <hr />
        <div class="import-box">
          <div><strong>重建向量知识库</strong><p>保存文件后,需要执行导入才能进入检索。</p></div>
          <button class="accent-button" type="button" :disabled="importPolling" @click="startImport">
            <i class="ph ph-cpu" aria-hidden="true"></i>
            {{ importPolling ? "导入中…" : "后台导入" }}
          </button>
        </div>
        <div v-if="admin.jobId" class="job-status">
          任务状态：{{ admin.jobStatus }}{{ admin.jobError ? ` · ${admin.jobError}` : "" }}
          <div v-if="importPolling" class="job-progress-track"><div class="job-progress-bar"></div></div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <div><p class="eyebrow">知识库</p><h2>当前文件</h2></div>
          <span class="pill">{{ admin.knowledgeFiles.length }} 个文件</span>
        </div>
        <div class="toolbar-row">
          <input v-model="search" class="search-input" type="search" placeholder="搜索文件名…" aria-label="搜索知识文件" />
        </div>
        <div class="file-list">
          <div v-if="admin.knowledgeLoading" class="list-state skeleton">正在加载…</div>
          <div v-for="file in filteredFiles" :key="file.filename" class="file-row">
            <div>
              <strong>{{ file.filename }}</strong>
              <small>{{ formatSize(file.size) }} · {{ formatDateTime(file.updated_at) }}</small>
            </div>
            <button class="delete-button" type="button" :aria-label="`删除文件 ${file.filename}`" @click="remove(file.filename)">
              <i class="ph ph-trash" aria-hidden="true"></i><span>删除</span>
            </button>
          </div>
          <div v-if="!filteredFiles.length && !admin.knowledgeLoading" class="feature">
            {{ admin.knowledgeFiles.length ? "没有匹配的文件" : "暂无知识文件" }}
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
