import { beforeEach, describe, expect, it, vi } from "vitest";
import { parseStreamLine, streamChat } from "@/api/chat";

const storage = new Map<string, string>();

beforeEach(() => {
  storage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  });
});

describe("parseStreamLine", () => {
  it("忽略空行", () => {
    expect(parseStreamLine("   ")).toBeNull();
  });

  it("解析 token 与 error 事件", () => {
    expect(parseStreamLine('{"type":"token","content":"你好"}')).toEqual({
      type: "token",
      content: "你好",
    });
    expect(parseStreamLine('{"type":"error","detail":"失败"}')).toEqual({
      type: "error",
      detail: "失败",
    });
    expect(
      parseStreamLine(
        '{"type":"sources","knowledge_used":true,"sources":[{"label":"jvm.md","kind":"private"}]}',
      ),
    ).toEqual({
      type: "sources",
      knowledge_used: true,
      sources: [{ label: "jvm.md", kind: "private" }],
    });
  });

  it("拒绝损坏的 JSON", () => {
    expect(() => parseStreamLine("{broken")).toThrow();
  });
});

describe("streamChat", () => {
  it("聚合跨行 token，并消费没有结尾换行符的最后一个事件", async () => {
    const body = [
      '{"type":"token","content":"Hello "}',
      '{"type":"token","content":"world"}',
      '{"type":"sources","knowledge_used":true,"sources":[]}',
      '{"type":"done"}',
    ].join("\n");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: string[] = [];

    const answer = await streamChat(
      {
        userId: "user-1",
        sessionId: "session-1",
        message: "hello",
        idempotencyKey: "chat-command-1",
      },
      (event) => events.push(event.type),
    );

    expect(answer).toBe("Hello world");
    expect(events).toEqual(["token", "token", "sources", "done"]);
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers["Idempotency-Key"]).toBe("chat-command-1");
  });

  it("把服务端 error 事件转换为异常", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('{"type":"error","detail":"模型不可用"}\n', { status: 200 }),
      ),
    );

    await expect(
      streamChat(
        {
          userId: "user-1",
          sessionId: "session-1",
          message: "hello",
          idempotencyKey: "chat-command-1",
        },
        () => undefined,
      ),
    ).rejects.toThrow("模型不可用");
  });
});
