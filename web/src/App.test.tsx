import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { App } from "./App";

const batch = { batch_id: "qa-test", source_label: "Synthetic sample provider-directory batch", record_count: 12, exception_count: 3, records_with_issues: 3, issue_counts: { missing_required_field: 1, stale_verification: 1, possible_duplicate_provider_location: 1 }, severity_mix: { high: 1, medium: 2, low: 0 }, source_summary: { "payer directory": 2 }, data_notice: "This console is using synthetic sample data.", limitations: "Duplicate candidates require human review." };
const caseItem = { case_id: "case-1", record_id: "REC-1", provider_name: "Sample Provider", issue_code: "missing_required_field", severity: "high", field_name: "phone", source: "payer directory", review_status: "new", assigned_to: null, updated_at: "2026-06-26T00:00:00Z" };

function renderApp() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><App /></QueryClientProvider>); }

test("shows bounded-data labeling, filters queue, and opens case evidence", async () => {
  const fetchMock = vi.fn((url: string) => {
    if (url.includes("batches")) return Promise.resolve(new Response(JSON.stringify(batch)));
    if (url.includes("/api/cases/case-1")) return Promise.resolve(new Response(JSON.stringify({ case: caseItem, exception: { values: {} }, normalized_records: [{ values: { provider_name: "Sample Provider", phone: "" } }], recommendation: "verify_phone", explanation: "Phone is required.", notes: null, history: [], duplicate: null })));
    return Promise.resolve(new Response(JSON.stringify({ items: [caseItem], total: 1 })));
  });
  vi.stubGlobal("fetch", fetchMock);
  renderApp();
  expect(await screen.findByText("Decide with evidence, not automation.")).toBeInTheDocument();
  expect(screen.getByText(/synthetic sample data/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /missing required field/i }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("issue_code=missing_required_field"), undefined));
  fireEvent.click(await screen.findByText("Sample Provider"));
  expect(await screen.findByText("Phone is required.")).toBeInTheDocument();
});
