import { beforeEach, describe, expect, it, vi } from "vitest";
import { confirmTrainingProgram, proposeTrainingProgram } from "@/api/learning";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => undefined });
});

describe("training program workflow API", () => {
  it("sends a durable idempotency key for proposals", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ run_id: "run-1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await proposeTrainingProgram("user-1", "RAG", "program-command-1");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/agent-runs/training-program");
    expect(options.headers["Idempotency-Key"]).toBe("program-command-1");
  });

  it("confirms a specific owner-scoped run", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ run_id: "run-1", status: "completed" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await confirmTrainingProgram("user-1", "run-1");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/agent-runs/run-1/confirm");
    expect(JSON.parse(options.body)).toEqual({ user_id: "user-1" });
  });
});
