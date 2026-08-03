<script setup lang="ts">
// Markdown 渲染组件：流式阶段增量渲染，完成后统一经 DOMPurify 净化并高亮。
import { computed, defineAsyncComponent, defineComponent, h } from "vue";
import { renderMarkdown } from "@/lib/markdown";

// Markstream 的运行时和样式仅在真正开始流式回答时加载，避免增加普通页面首屏成本。
// 首次下载异步 chunk 时先用文本节点展示内容，既不留白也不会执行模型生成的 HTML。
const StreamingMarkdownFallback = defineComponent({
  props: {
    content: { type: String, required: true },
  },
  setup(fallbackProps) {
    return () => h(
      "div",
      { class: "streaming-markdown-fallback", style: { whiteSpace: "pre-wrap" } },
      fallbackProps.content,
    );
  },
});

const StreamingMarkdownContent = defineAsyncComponent({
  loader: () => import("@/components/StreamingMarkdownContent.vue"),
  loadingComponent: StreamingMarkdownFallback,
  delay: 0,
});

const props = defineProps<{
  content: string;
  streaming?: boolean;
}>();

// 流式阶段由 Markstream 处理未闭合 Markdown 和增量节点更新；流结束后只做一次
// 完整 marked + highlight.js + DOMPurify 渲染，保留既有代码块样式和安全边界。
const html = computed(() =>
  props.streaming ? "" : renderMarkdown(props.content, false),
);
</script>

<template>
  <div
    class="markdown-content"
    :aria-busy="streaming ? 'true' : undefined"
    aria-live="polite"
  >
    <StreamingMarkdownContent
      v-if="streaming"
      :content="content"
    />
    <div v-else v-html="html"></div>
  </div>
</template>
