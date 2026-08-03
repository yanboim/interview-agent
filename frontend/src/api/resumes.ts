// 简历上传、评估、优化稿编辑与 DOCX 导出的 API 封装。
import type { ResumeAnalysis, ResumeDocument, ResumeDraft } from "@/types";
import { apiFetch, expectOk, makeId } from "@/api/core";

export async function uploadResume(
  file: File,
  jobDescription: string,
): Promise<ResumeDocument> {
  const form = new FormData();
  form.append("file", file);
  form.append("job_description", jobDescription);
  const response = await apiFetch("/api/resumes", {
    method: "POST",
    headers: { "Idempotency-Key": makeId("resume-upload") },
    body: form,
  });
  await expectOk(response);
  return response.json();
}

export async function listResumes(): Promise<ResumeDocument[]> {
  const response = await apiFetch("/api/resumes");
  await expectOk(response);
  return response.json();
}

export async function getResume(resumeId: string): Promise<ResumeDocument> {
  const response = await apiFetch(`/api/resumes/${encodeURIComponent(resumeId)}`);
  await expectOk(response);
  return response.json();
}

export async function reanalyzeResume(
  resumeId: string,
  jobDescription: string,
): Promise<ResumeDocument> {
  const response = await apiFetch(
    `/api/resumes/${encodeURIComponent(resumeId)}/analyses`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": makeId("resume-analysis"),
      },
      body: JSON.stringify({ job_description: jobDescription }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function updateResumeDraft(
  analysisId: string,
  expectedRevision: number,
  draft: ResumeDraft,
): Promise<ResumeAnalysis> {
  const response = await apiFetch(
    `/api/resume-analyses/${encodeURIComponent(analysisId)}/draft`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        draft,
      }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function exportResumeDocx(
  analysisId: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiFetch(
    `/api/resume-analyses/${encodeURIComponent(analysisId)}/export.docx`,
  );
  await expectOk(response);
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  return {
    blob: await response.blob(),
    filename: match ? decodeURIComponent(match[1]) : "resume-optimized.docx",
  };
}

export async function deleteResume(resumeId: string): Promise<boolean> {
  const response = await apiFetch(
    `/api/resumes/${encodeURIComponent(resumeId)}`,
    { method: "DELETE" },
  );
  await expectOk(response);
  return (await response.json()).deleted;
}
