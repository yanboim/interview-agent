// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MarkdownContent from "@/components/MarkdownContent.vue";
import UiButton from "@/components/ui/UiButton.vue";
import { renderInlineMarkdown } from "@/lib/markdown";

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

  it("marks streaming output as busy without changing content", () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: "**正在生成**", streaming: true },
    });
    expect(wrapper.text()).toContain("正在生成");
    expect(wrapper.attributes("aria-busy")).toBe("true");
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
