import type {
  Company,
  GraphResponse,
  NodeDetail,
  QueueItem,
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
};
