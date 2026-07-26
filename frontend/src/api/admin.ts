import type {
  AdminAudit,
  AdminKnowledgeFile,
  AdminRuntime,
  AdminSummary,
  AdminUser,
  ProductEvent,
} from "@/types";
import { adminFetch, expectAdminOk } from "@/api/adminCore";

export async function fetchAdminSummary(): Promise<AdminSummary> {
  const response = await adminFetch("/api/admin/system-summary");
  await expectAdminOk(response);
  return response.json();
}

export async function fetchAdminRuntime(): Promise<AdminRuntime> {
  const response = await adminFetch("/api/admin/runtime");
  await expectAdminOk(response);
  return response.json();
}

export async function fetchAdminKnowledgeFiles(): Promise<AdminKnowledgeFile[]> {
  const response = await adminFetch("/api/admin/knowledge/files");
  await expectAdminOk(response);
  return response.json();
}

export async function uploadKnowledgeFile(filename: string, content: string): Promise<void> {
  const response = await adminFetch("/api/admin/knowledge/files", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content }),
  });
  await expectAdminOk(response);
}

export async function deleteKnowledgeFile(filename: string): Promise<void> {
  const response = await adminFetch(
    `/api/admin/knowledge/files/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );
  await expectAdminOk(response);
}

export async function enqueueKnowledgeImport(): Promise<{ job_id: string }> {
  const response = await adminFetch("/api/admin/jobs/knowledge-import", { method: "POST" });
  await expectAdminOk(response);
  return response.json();
}

export async function fetchImportJob(
  jobId: string,
): Promise<{ status: string; error?: string }> {
  const response = await adminFetch(`/api/admin/jobs/${encodeURIComponent(jobId)}`);
  await expectAdminOk(response);
  return response.json();
}

export async function fetchAdminUsers(): Promise<AdminUser[]> {
  const response = await adminFetch("/api/admin/users");
  await expectAdminOk(response);
  return response.json();
}

export async function fetchAdminAudits(limit = 100): Promise<AdminAudit[]> {
  const response = await adminFetch(`/api/admin/tool-audits?limit=${limit}`);
  await expectAdminOk(response);
  return response.json();
}

export async function fetchAdminProductEvents(limit = 500): Promise<ProductEvent[]> {
  const response = await adminFetch(`/api/admin/product-events?limit=${limit}`);
  await expectAdminOk(response);
  return response.json();
}
