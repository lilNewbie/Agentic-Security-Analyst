import type {
  Company,
  GraphResponse,
  IngestionJobStatus,
  NodeDetail,
  QueueItem,
  QuestionnaireResponse,
  Stats,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getCompany: (id: string) => request<Company>(`/api/company/${id}`),

  createCompany: (name: string) =>
    request<{ company_id: string }>("/api/company", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  getStats: (companyId: string) =>
    request<Stats>(`/api/company/${companyId}/stats`),

  getGraph: (companyId: string) =>
    request<GraphResponse>(`/api/company/${companyId}/graph`),

  getQueue: (companyId: string) =>
    request<QueueItem[]>(`/api/company/${companyId}/queue`),

  getNode: (companyId: string, rubricId: string) =>
    request<NodeDetail>(`/api/company/${companyId}/node/${rubricId}`),

  postCorrection: (
    companyId: string,
    rubricId: string,
    slot: string,
    value: unknown,
    span?: string
  ) =>
    request(`/api/company/${companyId}/correction`, {
      method: "POST",
      body: JSON.stringify({ rubric_id: rubricId, slot, value, span: span ?? "" }),
    }),

  resolveConflict: (conflictId: string, winningEntryId: string, note?: string) =>
    request(`/api/conflict/${conflictId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ winning_entry_id: winningEntryId, note: note ?? "" }),
    }),

  getQuestionnaire: (companyId: string) =>
    request<QuestionnaireResponse>(`/api/company/${companyId}/questionnaire`),

  uploadDocument: async (companyId: string, file: File, sourceType?: string): Promise<{ ingestion_job_id: string }> => {
    const form = new FormData();
    form.append("file", file);
    if (sourceType) form.append("source_type", sourceType);
    const res = await fetch(`${BASE}/api/company/${companyId}/documents`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status} ${text}`);
    }
    return res.json();
  },

  getIngestionStatus: (companyId: string, jobId: string) =>
    request<IngestionJobStatus>(`/api/company/${companyId}/ingestion/${jobId}`),
};
