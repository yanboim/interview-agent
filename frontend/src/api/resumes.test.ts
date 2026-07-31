import { beforeEach, describe, expect, it, vi } from "vitest";
import { updateResumeDraft, uploadResume } from "@/api/resumes";


beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("localStorage", {
    getItem: () => null,
    setItem: () => undefined,
  });
});


describe("resume API", () => {
  it("uploads multipart content with a durable idempotency key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ resume_id: "resume-1", status: "uploaded", analyses: [] }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "uuid-1" });
    const file = new File(["resume"], "resume.pdf", { type: "application/pdf" });

    await uploadResume(file, "Python工程师");

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers["Idempotency-Key"]).toBe("resume-upload-uuid-1");
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.headers["Content-Type"]).toBeUndefined();
  });

  it("sends optimistic revision when saving the draft", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          analysis_id: "analysis-1",
          resume_id: "resume-1",
          status: "ready",
          report: null,
          draft: null,
          warnings: [],
          revision: 4,
          created_at: "now",
          updated_at: "now",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const draft = {
      name: "张三",
      headline: "后端工程师",
      summary: "",
      sections: [],
      pending_questions: [],
    };

    await updateResumeDraft("analysis-1", 3, draft);

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      expected_revision: 3,
      draft,
    });
  });
});
