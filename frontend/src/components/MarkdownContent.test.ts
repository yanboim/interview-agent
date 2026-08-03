// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import MarkdownContent from "@/components/MarkdownContent.vue";
import UiButton from "@/components/ui/UiButton.vue";
import {
  normalizeCitationMarkdown,
  normalizeLooseMarkdown,
  renderInlineMarkdown,
  renderMarkdown,
} from "@/lib/markdown";

describe("MarkdownContent", () => {
  it("renders headings, tables and code without unsafe markup", async () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content:
          "# 标题\n\n| 项目 | 值 |\n| --- | --- |\n| 分数 | 8 |",
        streaming: false,
      },
    });

    expect(wrapper.find("h1").text()).toBe("标题");
    expect(wrapper.find("table").text()).toContain("分数");
    await wrapper.setProps({ content: '<img src="x" onerror="alert(1)">' });
    expect(wrapper.html()).not.toContain("onerror");
  });

  it("uses the streaming renderer while output is in progress", async () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: "**正在生成", streaming: true },
    });
    await vi.dynamicImportSettled();
    await flushPromises();
    expect(wrapper.text()).toContain("正在生成");
    expect(wrapper.attributes("aria-busy")).toBe("true");
    expect(wrapper.find(".markstream-vue").exists()).toBe(true);

    await wrapper.setProps({ content: "**生成完成**", streaming: false });
    expect(wrapper.find(".markstream-vue").exists()).toBe(false);
    expect(wrapper.find("strong").text()).toBe("生成完成");
    expect(wrapper.attributes("aria-busy")).toBeUndefined();
  });

  it("does not activate unsafe HTML during streaming", async () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: '安全文本\n\n<img src="x" onerror="alert(1)">',
        streaming: true,
      },
    });
    await vi.dynamicImportSettled();
    await flushPromises();

    expect(wrapper.html()).not.toContain("onerror");
    expect(wrapper.text()).toContain("安全文本");
  });
});

describe("normalizeCitationMarkdown", () => {
  it("repairs citation emphasis spacing and removes an orphan trailing marker", () => {
    const normalized = normalizeCitationMarkdown(
      "> ⚠️ 使用 **SATB (Snapshot-At-The-Beginning) ** 与 `JDK 21`。 ``",
    );
    const html = renderMarkdown(normalized);

    expect(normalized).toBe(
      "> ⚠️ 使用 **SATB (Snapshot-At-The-Beginning)** 与 `JDK 21`。",
    );
    expect(html).toContain("<blockquote>");
    expect(html).toContain("<strong>SATB (Snapshot-At-The-Beginning)</strong>");
    expect(html).toContain("<code>JDK 21</code>");
    expect(html).not.toContain("``");
  });
});

describe("UiButton", () => {
  it("exposes loading state and blocks duplicate clicks", async () => {
    const wrapper = mount(UiButton, {
      props: { loading: true },
      slots: { default: "保存" },
    });
    expect(wrapper.attributes("disabled")).toBeDefined();
    expect(wrapper.attributes("aria-busy")).toBe("true");
  });
});

describe("renderInlineMarkdown", () => {
  it("renders question emphasis without allowing block or unsafe markup", () => {
    const html = renderInlineMarkdown(
      "解释 **动态重规划** 与 `retry` <img src=x onerror=alert(1)>",
    );

    expect(html).toContain("<strong>动态重规划</strong>");
    expect(html).toContain("<code>retry</code>");
    expect(html).not.toContain("**");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("onerror");
  });
});

describe("normalizeLooseMarkdown", () => {
  it("repairs compact numbered sections, bullets and emphasis spacing", () => {
    const compact =
      "先说明原则。  1. **通信机制设计 **： - 局部智能体自治。 "
      + "- **意图黑板**：广播意图。  2. **冲突仲裁**： - 检测环路。";
    const normalized = normalizeLooseMarkdown(compact);
    const html = renderMarkdown(normalized);

    expect(normalized).toContain("\n\n1. **通信机制设计**：\n\n- 局部智能体自治。");
    expect(normalized).toContain("\n- **意图黑板**：广播意图。");
    expect(normalized).toContain("\n\n2. **冲突仲裁**：\n\n- 检测环路。");
    expect(html).toContain("<ol>");
    expect(html).toContain("<ul>");
    expect(html).toContain("<strong>通信机制设计</strong>");
    expect(html).not.toContain("**");
  });
});
