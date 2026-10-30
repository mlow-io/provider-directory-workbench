import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { api } from "./api";
import type { CaseAction, ReviewCase } from "./types";
import { RemediationWorkspace } from "./RemediationWorkspace";
import { IntakeWorkbench, type IntakePage } from "./IntakeWorkbench";

type Filters = { search: string; severity: string; issueCode: string; status: string; sort: string; direction: "asc" | "desc" };
const initialFilters: Filters = { search: "", severity: "", issueCode: "", status: "", sort: "priority", direction: "asc" };
const column = createColumnHelper<ReviewCase>();

function pretty(value: string) { return value.replaceAll("_", " "); }
function timestamp(value: string) { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }

export function App() {
  const initialView = new URLSearchParams(window.location.search).get("view") || "qa";
  const [workspace, setWorkspace] = useState(initialView);
  useEffect(() => { const update = () => setWorkspace(new URLSearchParams(window.location.search).get("view") || "qa"); window.addEventListener("popstate", update); return () => window.removeEventListener("popstate", update); }, []);
  const navigate = (view: string) => { const query = new URLSearchParams(window.location.search); query.set("view", view); history.pushState(null, "", `?${query}`); setWorkspace(view); };
  return <><nav className="iw-nav" aria-label="Workbench navigation">{[["intake", "Intake"], ["work", "Work queue"], ["sources", "Sources"], ["qa", "Legacy QA"], ["remediation", "Corrections"]].map(([view, label]) => <a key={view} href={`?view=${view}`} aria-current={workspace === view ? "page" : undefined} onClick={event => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey) { event.preventDefault(); navigate(view); } }}>{label}</a>)}</nav>{["intake", "work", "sources"].includes(workspace) ? <IntakeWorkbench page={workspace as IntakePage} /> : workspace === "remediation" ? <RemediationWorkspace onExit={() => navigate("qa")} /> : <ReviewConsole onOpenRemediation={() => navigate("remediation")} />}</>;
}

function ReviewConsole({ onOpenRemediation }: { onOpenRemediation: () => void }) {
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const batch = useQuery({ queryKey: ["batch"], queryFn: api.batch });
  const params = useMemo(() => {
    const next = new URLSearchParams();
    if (filters.search) next.set("search", filters.search);
    if (filters.severity) next.set("severity", filters.severity);
    if (filters.issueCode) next.set("issue_code", filters.issueCode);
    if (filters.status) next.set("status", filters.status);
    next.set("sort", filters.sort); next.set("direction", filters.direction);
    return next;
  }, [filters]);
  const cases = useQuery({ queryKey: ["cases", params.toString()], queryFn: () => api.cases(params) });
  const detail = useQuery({ queryKey: ["detail", selectedCase], queryFn: () => api.detail(selectedCase!), enabled: Boolean(selectedCase) });
  const setFilter = (key: keyof Filters, value: string) => setFilters((current) => ({ ...current, [key]: value }));
  const chooseIssue = (issueCode: string) => { setFilters({ ...initialFilters, issueCode }); setSelectedCase(null); };
  const exportUrl = `/api/exports/cases.csv?${params}`;

  const columns = useMemo(() => [
    column.accessor("provider_name", { header: "Provider", cell: (info) => <><strong>{info.getValue()}</strong><span className="muted mono">{info.row.original.record_id}</span></> }),
    column.accessor("issue_code", { header: "Failed rule", cell: (info) => <span className="rule">{pretty(info.getValue())}</span> }),
    column.accessor("severity", { header: "Severity", cell: (info) => <span className={`tag tag-${info.getValue()}`}>{info.getValue()}</span> }),
    column.accessor("review_status", { header: "Review", cell: (info) => <span className={`status status-${info.getValue()}`}>{pretty(info.getValue())}</span> }),
    column.accessor("assigned_to", { header: "Owner", cell: (info) => info.getValue() || <span className="muted">Unassigned</span> }),
  ], []);
  const table = useReactTable({ data: cases.data?.items ?? [], columns, getCoreRowModel: getCoreRowModel() });
  const sortName = (columnId: string) => ({ provider_name: "provider", review_status: "status", assigned_to: "owner" }[columnId] ?? columnId);

  if (batch.isLoading || cases.isLoading) return <main className="loading">Preparing review queue…</main>;
  if (batch.isError || cases.isError) return <main className="loading error">Unable to load the local review batch. Run <code>make demo</code> and start the API.</main>;
  const currentBatch = batch.data!;

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark" aria-hidden="true">▦</span><div><p>Directory Review Console</p><span>Evidence-led exception review</span></div></div>
      <div className="topbar-actions"><button className="button button-secondary remediation-entry" onClick={onOpenRemediation}>Open remediation loop →</button><div className="batch-chip"><span className="pulse" /> Batch <code>{currentBatch.batch_id}</code></div></div>
    </header>

    <section className="notice" aria-label="Data limitation"><span aria-hidden="true">ⓘ</span><p><strong>Bounded review data.</strong> {currentBatch.data_notice}</p><span>{currentBatch.limitations}</span></section>

    <section className="overview" aria-labelledby="overview-heading">
      <div className="section-heading"><div><p className="eyebrow">Review overview</p><h1 id="overview-heading">Decide with evidence, not automation.</h1><p>{currentBatch.source_label} <span aria-hidden="true">·</span> {currentBatch.record_count} records reviewed</p></div><a className="button button-secondary" href="/api/exports/batch.csv">↓ Export batch</a></div>
      <div className="metric-grid">
        <Metric label="Exceptions" value={currentBatch.exception_count} hint={`${currentBatch.records_with_issues} records affected`} />
        <Metric label="Open queue" value={cases.data!.items.filter((item) => item.review_status !== "resolved").length} hint="in the current filter" />
        <Metric label="Sources" value={Object.keys(currentBatch.source_summary).length} hint="contributing systems" />
        <div className="metric severity-mix"><p>Severity mix</p><div>{["high", "medium", "low"].map((level) => <span key={level} className={`tag tag-${level}`}>{level} {currentBatch.severity_mix[level] ?? 0}</span>)}</div></div>
      </div>
      <div className="overview-meta"><div className="source-summary" aria-label="Source summary"><span>Source contribution</span>{Object.entries(currentBatch.source_summary).map(([source, count]) => <span key={source}><b>{count}</b> {source}</span>)}</div><div className="issue-links" aria-label="Filter queue by issue type">{Object.entries(currentBatch.issue_counts).map(([issue, count]) => <button key={issue} onClick={() => chooseIssue(issue)}><span>{pretty(issue)}</span><b>{count}</b> <span aria-hidden="true">→</span></button>)}</div></div>
    </section>

    <section className="workspace" aria-label="Review workspace">
      <div className="queue-card">
        <div className="queue-top"><div><p className="eyebrow">Exception queue</p><h2>{cases.data!.total} cases <span>requiring a review decision</span></h2></div><a className="button button-secondary" href={exportUrl}>↓ Export view</a></div>
        <div className="filters">
          <label className="search"><span aria-hidden="true">⌕</span><input aria-label="Search cases" placeholder="Search provider, record, or rule" value={filters.search} onChange={(event) => setFilter("search", event.target.value)} /></label>
          <label>Severity<select aria-label="Severity filter" value={filters.severity} onChange={(event) => setFilter("severity", event.target.value)}><option value="">All</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
          <label>Review<select aria-label="Review status filter" value={filters.status} onChange={(event) => setFilter("status", event.target.value)}><option value="">All</option>{["new", "assigned", "in_review", "deferred", "resolved"].map((status) => <option key={status} value={status}>{pretty(status)}</option>)}</select></label>
          <button className="text-button" onClick={() => { setFilters(initialFilters); setSelectedCase(null); }}>Reset</button>
        </div>
        <div className="table-wrap"><table><thead>{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th key={header.id} scope="col"><button onClick={() => setFilters((current) => { const nextSort = sortName(header.column.id); return { ...current, sort: nextSort, direction: current.sort === nextSort ? (current.direction === "asc" ? "desc" : "asc") : "asc" }; })}>{flexRender(header.column.columnDef.header, header.getContext())}<span aria-hidden="true"> ↕</span></button></th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map((row) => <tr className={selectedCase === row.original.case_id ? "selected" : ""} key={row.id} onClick={() => setSelectedCase(row.original.case_id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedCase(row.original.case_id); } }} aria-label={`Open case for ${row.original.provider_name}`}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table></div>
      </div>
      <aside className="detail-card" aria-live="polite">{detail.isLoading && <p className="empty">Loading case evidence…</p>}{!selectedCase && <div className="empty"><span aria-hidden="true">↗</span><h2>Select a case</h2><p>Open a queue item to inspect evidence, record a decision, and preserve the audit history.</p></div>}{detail.data && <CasePanel detail={detail.data} />}</aside>
    </section>
  </main>;
}

function Metric({ label, value, hint }: { label: string; value: number; hint: string }) { return <div className="metric"><p>{label}</p><strong>{value}</strong><span>{hint}</span></div>; }

function CasePanel({ detail }: { detail: import("./types").CaseDetail }) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<CaseAction>("assign");
  const [assignee, setAssignee] = useState(""); const [reason, setReason] = useState(""); const [note, setNote] = useState("");
  const transition = useMutation({ mutationFn: () => api.transition(detail.case.case_id, { action, assignee: assignee || undefined, reason, note: note || undefined }), onSuccess: () => { setReason(""); setNote(""); queryClient.invalidateQueries({ queryKey: ["cases"] }); queryClient.invalidateQueries({ queryKey: ["detail", detail.case.case_id] }); }, });
  return <div className="case-panel">
    <div className="case-title"><div><p className="eyebrow">Case briefing · {detail.case.case_id.slice(-6)}</p><h2>{detail.case.provider_name}</h2></div><div className="case-badges"><span className={`tag tag-${detail.case.severity}`}>{detail.case.severity}</span><span className={`status status-${detail.case.review_status}`}>{pretty(detail.case.review_status)}</span></div></div>
    <div className="rule-callout"><span aria-hidden="true">!</span><div><strong>{pretty(detail.case.issue_code)}</strong><p>{detail.explanation}</p><small>Recommended: {pretty(detail.recommendation)}</small></div></div>
    <section className="case-context"><h3>Case context</h3><dl className="facts"><Fact label="Record" value={detail.case.record_id} /><Fact label="Source" value={detail.case.source} /><Fact label="Failed field" value={detail.case.field_name} /><Fact label="Current owner" value={detail.case.assigned_to || "Unassigned"} /></dl></section>
    <section className="evidence-section"><div className="section-title"><div><h3>{detail.duplicate ? "Candidate comparison" : "Normalized evidence"}</h3><p>{detail.duplicate ? "Review the records side by side before resolving this candidate." : "Normalized values supplied for this exception."}</p></div><span className="evidence-count">{detail.normalized_records.length} record{detail.normalized_records.length === 1 ? "" : "s"}</span></div>{detail.duplicate && <p className="warning">⚠ {detail.duplicate.warning}</p>}<EvidenceMatrix records={detail.duplicate?.records ?? detail.normalized_records} /></section>
    <section className="action-panel"><h3>Record review event</h3><label>Action<select value={action} onChange={(event) => setAction(event.target.value as CaseAction)}>{["assign", "start_review", "resolve", "defer", "add_note"].map((value) => <option key={value} value={value}>{pretty(value)}</option>)}</select></label>{action === "assign" && <label>Assignee<input placeholder="Reviewer name" value={assignee} onChange={(event) => setAssignee(event.target.value)} /></label>}<label>Reason <em>required</em><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why is this change needed?" /></label><label>Notes <span>optional</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add review evidence or a follow-up detail" rows={3} /></label>{transition.isError && <p className="form-error">{transition.error.message}</p>}<button className="button button-primary" disabled={!reason || (action === "assign" && !assignee) || transition.isPending} onClick={() => transition.mutate()}>{transition.isPending ? "Saving…" : "Save event"}</button></section>
    <section><h3>Append-only history</h3>{detail.history.length === 0 ? <p className="muted">No review events yet.</p> : <ol className="history">{detail.history.map((event) => <li key={event.event_id}><b>{pretty(event.event_type)}</b><span>{event.reason}</span>{event.note && <small>{event.note}</small>}<time>{timestamp(event.occurred_at)}</time></li>)}</ol>}</section>
  </div>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }

function EvidenceMatrix({ records }: { records: Array<{ values: Record<string, unknown> }> }) {
  const fields = ["record_id", "provider_name", "specialty", "address", "city", "state", "phone", "last_verified_date", "source"];
  const visibleFields = fields.filter((field) => records.some((record) => record.values[field] !== undefined));
  return <div className="evidence-matrix" role="region" aria-label="Normalized record comparison"><table><thead><tr><th scope="col">Field</th>{records.map((_, index) => <th key={index} scope="col">Record {index + 1}</th>)}</tr></thead><tbody>{visibleFields.map((field) => <tr key={field}><th scope="row">{pretty(field)}</th>{records.map((record, index) => <td key={index}>{String(record.values[field] ?? "—")}</td>)}</tr>)}</tbody></table></div>;
}
