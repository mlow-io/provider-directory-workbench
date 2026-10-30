import type {
  BatchSummary,
  CaseDetail,
  CasePage,
  RemediationCaseDetail,
  RemediationCasePage,
  RemediationTransitionInput,
  TransitionInput,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export const api = {
  batch: () => request<BatchSummary>("/api/batches/current"),
  cases: (params: URLSearchParams) => request<CasePage>(`/api/cases?${params}`),
  detail: (caseId: string) => request<CaseDetail>(`/api/cases/${caseId}`),
  transition: (caseId: string, payload: TransitionInput) => request(`/api/cases/${caseId}/transitions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
};

export const remediationApi = {
  cases: (params: URLSearchParams) => request<RemediationCasePage>(`/api/remediation/cases?${params}`),
  detail: (caseId: string) => request<RemediationCaseDetail>(`/api/remediation/cases/${caseId}`),
  transition: (caseId: string, payload: RemediationTransitionInput) => request(`/api/remediation/cases/${caseId}/transitions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
};
