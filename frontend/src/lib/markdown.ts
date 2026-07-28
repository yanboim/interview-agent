import DOMPurify from "dompurify";
import { marked } from "marked";
import hljs from "highlight.js/lib/common";

// 配置 marked:启用 GFM、换行转 <br>,并对代码块做语法高亮 + 复制按钮钩子。
marked.setOptions({
  gfm: true,
  breaks: true,
});

function codeBlock(label: string, language: string, content: string): string {
  return (
    `<div class="code-block"><div class="code-toolbar">${label}`
    + '<button type="button" class="copy-code">复制</button></div>'
    + `<pre><code class="hljs language-${escapeHtml(language || "text")}">${content}</code></pre></div>`
  );
}

// 完整 renderer:回答结束后执行语法高亮和未知语言自动识别。
const highlightedRenderer = new marked.Renderer();
highlightedRenderer.code = ({ text, lang }: { text: string; lang?: string }) => {
  const language = lang && hljs.getLanguage(lang) ? lang : "";
  let highlighted: string;
  try {
    highlighted = language
      ? hljs.highlight(text, { language }).value
      : hljs.highlightAuto(text).value;
  } catch {
    highlighted = escapeHtml(text);
  }
  const label = language
    ? `<span class="code-language">${escapeHtml(language)}</span>`
    : "<span>代码</span>";
  return codeBlock(label, language, highlighted);
};

// 流式 renderer:避免每个渲染帧都运行 highlightAuto。文本仍经过转义和 DOMPurify。
const streamingRenderer = new marked.Renderer();
streamingRenderer.code = ({ text, lang }: { text: string; lang?: string }) => {
  const language = lang && hljs.getLanguage(lang) ? lang : "";
  const label = language
    ? `<span class="code-language">${escapeHtml(language)}</span>`
    : "<span>代码</span>";
  return codeBlock(label, language, escapeHtml(text));
};

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/** 将 Markdown 渲染为经过净化的安全 HTML。流式阶段可跳过昂贵的代码高亮。 */
export function renderMarkdown(source: string, streaming = false): string {
  const raw = marked.parse(source || "", {
    async: false,
    renderer: streaming ? streamingRenderer : highlightedRenderer,
  }) as string;
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ["target", "rel"],
  });
}

/**
 * Render the small inline Markdown subset used inside question headings.
 * Block elements and media are deliberately excluded so model output cannot
 * break the interview layout.
 */
export function renderInlineMarkdown(source: string): string {
  const raw = marked.parseInline(source || "", { async: false }) as string;
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: ["a", "br", "code", "del", "em", "strong"],
    ALLOWED_ATTR: ["href", "rel", "target", "title"],
  });
}

/**
 * Repair compact Markdown commonly returned inside structured model fields.
 * This is intentionally opt-in for reference answers; chat content is left
 * untouched. The rules only split explicit numbered bold sections and
 * sentence-delimited bullet markers.
 */
export function normalizeLooseMarkdown(source: string): string {
  return (source || "")
    .replaceAll("\r\n", "\n")
    .replaceAll("\r", "\n")
    .replace(/\*\*([^*\n]*?\S)\s+\*\*(?=[：:])/gu, "**$1**")
    .replace(/([。！？；;])\s+(\d{1,2}\.\s+\*\*)/gu, "$1\n\n$2")
    .replace(/(\*\*[^*\n]{1,100}\*\*[：:])\s*-\s+/gu, "$1\n\n- ")
    .replace(
      /([。！？；;])\s+-\s+(?=(?:\*\*)?[\p{L}\p{N}])/gu,
      "$1\n- ",
    )
    .trim();
}

export function escapeText(value: unknown): string {
  return escapeHtml(String(value ?? ""));
}
