import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { App } from "./App";

const remediationCase = {
  case_id: "remediation-1", listing_id: "PAYER-00002", reference_provider_key: "npi:1234567890",
  field_name: "state", status: "new", risk_level: "high", active_proposed_correction_value: null,
  updated_at: "2026-06-26T00:00:00Z",
};
const evidence = { listing_value: "GA", reference_value: "TN", reference_source: "clinic directory", reference_record_id: "REC-1", precedence_rank: 1, comparison_status: "discrepancy", risk_reason: "Operational review required.", listing_comparison_value: "GA", reference_comparison_value: "TN" };

function renderApp() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><App /></QueryClientProvider>); }

test("opens remediation evidence and submits a human triage event through the separate API", async () => {
  let status = "new";
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes("batches")) return Promise.resolve(new Response(JSON.stringify({ batch_id: "qa-test", source_label: "Synthetic", record_count: 1, exception_count: 1, records_with_issues: 1, issue_counts: {}, severity_mix: {}, source_summary: {}, data_notice: "Synthetic", limitations: "Bounded" })));
    if (url.includes("/api/remediation/cases/remediation-1/transitions")) { status = "triaged"; return Promise.resolve(new Response(JSON.stringify({ case: { ...remediationCase, status }, event: {} }))); }
    if (url.includes("/api/remediation/cases/remediation-1")) return Promise.resolve(new Response(JSON.stringify({ case: { ...remediationCase, status }, evidence: { values: evidence }, history: [] })));
    if (url.includes("/api/remediation/cases?") || url.endsWith("/api/remediation/cases")) return Promise.resolve(new Response(JSON.stringify({ items: [{ ...remediationCase, status }], total: 1 })));
    return Promise.resolve(new Response(JSON.stringify({ items: [], total: 0 })));
  });
  vi.stubGlobal("fetch", fetchMock);
  renderApp();

  fireEvent.click(await screen.findByRole("button", { name: /open remediation loop/i }));
  expect(await screen.findByRole("heading", { name: "Follow the evidence through verification." })).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("row", { name: /open remediation case payer-00002, state/i }));
  expect(await screen.findByText("Comparison / reference value")).toBeInTheDocument();
  expect(screen.getByText("not certified truth", { exact: false })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "triage" }));
  fireEvent.change(screen.getByLabelText("Remediation actor"), { target: { value: "Morgan" } });
  fireEvent.change(screen.getByLabelText("Remediation reason"), { target: { value: "Review the payer-state discrepancy" } });
  fireEvent.click(screen.getByRole("button", { name: "Record triage" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/remediation/cases/remediation-1/transitions"), expect.objectContaining({ method: "POST" })));
});
