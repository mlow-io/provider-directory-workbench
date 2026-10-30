import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { remediationApi } from "./api";
import type {
  RemediationAction,
  RemediationCase,
  RemediationCaseDetail,
  RemediationStatus,
  RemediationTransitionInput,
} from "./types";

type Filters = { status: string; riskLevel: string; fieldName: string };
const initialFilters: Filters = { status: "", riskLevel: "", fieldName: "" };
const fields = ["npi", "provider_name", "specialty", "address", "city", "state", "zip", "phone", "accepting_new_patients", "status"];

function pretty(value: string) { return value.replaceAll("_", " "); }
function timestamp(value: string) { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function display(value: unknown) { return value === null || value === undefined || value === "" ? "—" : String(value); }

function availableActions(status: RemediationStatus): RemediationAction[] {
  if (status === "new") return ["triage", "defer"];
  if (status === "triaged") return ["approve", "defer"];
  if (status === "reopened") return ["triage", "defer"];
  if (status === "deferred") return ["triage"];
  if (status === "approved") return ["submit"];
  if (status === "pending_verification") return ["verify"];
  return [];
}

export function RemediationWorkspace({ onExit }: { onExit: () => void }) {
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const params = useMemo(() => {
    const next = new URLSearchParams();
    if (filters.status) next.set("status", filters.status);
    if (filters.riskLevel) next.set("risk_level", filters.riskLevel);
    if (filters.fieldName) next.set("field_name", filters.fieldName);
    return next;
  }, [filters]);
  const cases = useQuery({ queryKey: ["remediationCases", params.toString()], queryFn: () => remediationApi.cases(params) });
  const detail = useQuery({ queryKey: ["remediationDetail", selectedCase], queryFn: () => remediationApi.detail(selectedCase!), enabled: Boolean(selectedCase) });
  const setFilter = (key: keyof Filters, value: string) => setFilters((current) => ({ ...current, [key]: value }));

  return <main className="app-shell remediation-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark" aria-hidden="true">⇄</span><div><p>Directory Remediation</p><span>Human-controlled payer verification</span></div></div>
      <button className="button button-secondary workspace-switch" onClick={onExit}>← QA exception review</button>
    </header>

    <section className="remediation-notice" aria-label="Remediation scope">
      <strong>Human judgment, recorded.</strong>
      <span>These are synthetic payer-directory discrepancies. Approval records a proposed correction; it never changes provider truth or sends a payer update.</span>
    </section>

    <section className="remediation-heading" aria-labelledby="remediation-heading">
      <div><p className="eyebrow">Payer directory loop</p><h1 id="remediation-heading">Follow the evidence through verification.</h1><p>Inspect the stored comparison, make a reasoned proposal, and record what the payer actually shows.</p></div>
      <div className="loop-key" aria-label="Workflow stages"><span>Evidence</span><b>→</b><span>Human proposal</span><b>→</b><span>Observed verification</span></div>
    </section>

    {cases.isLoading ? <section className="remediation-state">Loading the remediation queue…</section> : null}
    {cases.isError ? <section className="remediation-state remediation-error"><h2>Remediation evidence is unavailable</h2><p>{cases.error instanceof Error ? cases.error.message : "The local remediation API could not be reached."}</p><code>make demo</code><span> then start both local APIs before opening this workspace.</span></section> : null}
    {cases.data ? <section className="remediation-workspace" aria-label="Remediation workspace">
      <section className="remediation-queue">
        <div className="queue-top"><div><p className="eyebrow">Field discrepancy queue</p><h2>{cases.data.total} case{cases.data.total === 1 ? "" : "s"} <span>available for human action</span></h2></div><button className="text-button" onClick={() => { setFilters(initialFilters); setSelectedCase(null); }}>Reset filters</button></div>
        <div className="filters remediation-filters">
          <label>Status<select aria-label="Remediation status filter" value={filters.status} onChange={(event) => setFilter("status", event.target.value)}><option value="">All statuses</option>{["new", "triaged", "approved", "pending_verification", "reopened", "verified", "deferred"].map((status) => <option key={status} value={status}>{pretty(status)}</option>)}</select></label>
          <label>Risk<select aria-label="Remediation risk filter" value={filters.riskLevel} onChange={(event) => setFilter("riskLevel", event.target.value)}><option value="">All risks</option>{["high", "medium", "low"].map((risk) => <option key={risk} value={risk}>{risk}</option>)}</select></label>
          <label>Field<select aria-label="Remediation field filter" value={filters.fieldName} onChange={(event) => setFilter("fieldName", event.target.value)}><option value="">All fields</option>{fields.map((field) => <option key={field} value={field}>{pretty(field)}</option>)}</select></label>
        </div>
        {cases.data.items.length === 0 ? <div className="queue-empty"><strong>No remediation cases match these filters.</strong><span>Try clearing a filter, or run the explicit synthetic payer demo to create evidence.</span></div> : <div className="table-wrap remediation-table-wrap"><table><thead><tr><th scope="col">Listing / reference</th><th scope="col">Field</th><th scope="col">Risk</th><th scope="col">Workflow</th><th scope="col">Active proposal</th><th scope="col">Updated</th></tr></thead><tbody>{cases.data.items.map((item) => <RemediationRow key={item.case_id} item={item} selected={selectedCase === item.case_id} onSelect={() => setSelectedCase(item.case_id)} />)}</tbody></table></div>}
      </section>
      <aside className="detail-card remediation-detail" aria-live="polite">
        {detail.isLoading ? <p className="empty">Loading immutable evidence…</p> : null}
        {!selectedCase ? <div className="empty remediation-empty"><span aria-hidden="true">⇄</span><h2>Open a discrepancy</h2><p>Start with the payer-listed value, then record the human decision and the observed verification result.</p></div> : null}
        {detail.isError ? <div className="detail-error"><h2>Case could not be refreshed</h2><p>{detail.error instanceof Error ? detail.error.message : "Please select the case again."}</p></div> : null}
        {detail.data ? <RemediationCasePanel detail={detail.data} /> : null}
      </aside>
    </section> : null}
  </main>;
}

function RemediationRow({ item, selected, onSelect }: { item: RemediationCase; selected: boolean; onSelect: () => void }) {
  return <tr className={`${selected ? "selected" : ""} ${item.status === "reopened" ? "reopened-row" : ""}`} onClick={onSelect} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(); } }} aria-label={`Open remediation case ${item.listing_id}, ${pretty(item.field_name)}`}>
    <td><strong>{item.listing_id}</strong><span className="muted mono">{item.reference_provider_key}</span></td>
    <td><span className="rule">{pretty(item.field_name)}</span></td>
    <td><RiskTag risk={item.risk_level} /></td>
    <td><StatusTag status={item.status} /></td>
    <td className="proposal-cell">{item.active_proposed_correction_value ? item.active_proposed_correction_value : <span className="muted">Not approved</span>}</td>
    <td><time className="muted">{timestamp(item.updated_at)}</time></td>
  </tr>;
}

function RiskTag({ risk }: { risk: string }) { return <span className={`tag tag-${risk}`}><span aria-hidden="true">{risk === "high" ? "! " : ""}</span>{risk} risk</span>; }
function StatusTag({ status }: { status: string }) { return <span className={`status remediation-status status-${status}`}><span aria-hidden="true">{status === "reopened" ? "↻ " : ""}</span>{pretty(status)}</span>; }

function RemediationCasePanel({ detail }: { detail: RemediationCaseDetail }) {
  const evidence = detail.evidence.values;
  const observed = [...detail.history].reverse().find((event) => event.observed_payer_value !== null)?.observed_payer_value;
  const legacy = evidence.snapshot_status === "legacy_evidence_unavailable_when_snapshot_migrated";
  const provenance = ["listing_id", "provider_key", "field_name", "risk_level", "reference_source", "reference_record_id", "precedence_rank", "comparison_status", "risk_reason", "listing_comparison_value", "reference_comparison_value"];
  return <div className="case-panel remediation-panel">
    <div className="case-title"><div><p className="eyebrow">Remediation case · {detail.case.case_id.slice(-8)}</p><h2>{detail.case.listing_id} <span className="muted">/ {pretty(detail.case.field_name)}</span></h2><p className="case-subtitle">Reference key: <code>{detail.case.reference_provider_key}</code></p></div><div className="case-badges"><RiskTag risk={detail.case.risk_level} /><StatusTag status={detail.case.status} /></div></div>
    {legacy ? <div className="legacy-notice"><strong>Legacy evidence snapshot</strong><p>The original Phase 1 row was unavailable when this older case was migrated. The preserved case identity and event history remain reviewable; do not infer missing source details.</p></div> : <div className="reference-notice"><strong>Comparison reference, not certified truth.</strong><p>The source-selected reference supports review. It is not an authoritative provider record or automatic correction instruction.</p></div>}
    <section className="value-lanes" aria-label="Remediation value comparison">
      <ValueLane label="Payer-listed value" value={display(evidence.listing_value)} tone="payer" />
      <ValueLane label="Comparison / reference value" value={display(evidence.reference_value)} tone="reference" />
      <ValueLane label="Active human proposal" value={display(detail.case.active_proposed_correction_value)} tone="proposal" />
      <ValueLane label="Observed verification value" value={display(observed)} tone="observed" />
    </section>
    <section className="case-context"><h3>Stored evidence & provenance</h3><dl className="facts remediation-facts"><Fact label="Payer listing" value={detail.case.listing_id} /><Fact label="Reference provider" value={detail.case.reference_provider_key} /><Fact label="Field" value={pretty(detail.case.field_name)} /><Fact label="Risk" value={detail.case.risk_level} /><Fact label="Reference source" value={display(evidence.reference_source)} /><Fact label="Source record" value={display(evidence.reference_record_id)} /><Fact label="Comparison status" value={pretty(display(evidence.comparison_status))} /><Fact label="Precedence rank" value={display(evidence.precedence_rank)} /></dl></section>
    {!legacy ? <section className="snapshot-section"><div className="section-title"><div><h3>Immutable Phase 1 snapshot</h3><p>Stored when this case was first inserted. Pipeline reruns cannot replace it.</p></div></div><dl className="snapshot-facts">{provenance.filter((key) => evidence[key] !== undefined).map((key) => <Fact key={key} label={pretty(key)} value={display(evidence[key])} />)}</dl></section> : null}
    <RemediationControls detail={detail} />
    <HistoryTimeline history={detail.history} />
  </div>;
}

function ValueLane({ label, value, tone }: { label: string; value: string; tone: string }) { return <div className={`value-lane value-${tone}`}><span>{label}</span><strong>{value}</strong></div>; }
function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }

function RemediationControls({ detail }: { detail: RemediationCaseDetail }) {
  const queryClient = useQueryClient();
  const actions = availableActions(detail.case.status);
  const [action, setAction] = useState<RemediationAction | null>(actions[0] ?? null);
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [proposal, setProposal] = useState("");
  const [submissionReference, setSubmissionReference] = useState("");
  const [observedValue, setObservedValue] = useState("");
  const [verificationNote, setVerificationNote] = useState("");
  const [recorded, setRecorded] = useState(false);
  useEffect(() => { setAction(actions[0] ?? null); setReason(""); setProposal(""); setSubmissionReference(""); setObservedValue(""); setVerificationNote(""); }, [detail.case.case_id, detail.case.status]);
  const mutation = useMutation({
    mutationFn: (payload: RemediationTransitionInput) => remediationApi.transition(detail.case.case_id, payload),
    onSuccess: () => {
      setRecorded(true);
      queryClient.invalidateQueries({ queryKey: ["remediationCases"] });
      queryClient.invalidateQueries({ queryKey: ["remediationDetail", detail.case.case_id] });
    },
  });
  if (actions.length === 0 || !action) return <section className="workflow-complete"><h3>Workflow state</h3><p>{detail.case.status === "verified" ? "Verification is recorded as matched to the active human-approved proposal." : "This case has no further Phase 3 action available."}</p>{recorded ? <p className="form-success" role="status">Event recorded. The queue, case, and audit history were refreshed.</p> : null}</section>;
  const explanation: Record<RemediationAction, string> = {
    triage: "Records the named actor and reason for beginning human review. No data is changed.",
    defer: "Records why a human is deferring this case. No data is changed.",
    approve: "Records the proposed correction alongside the stored payer and comparison values. It does not write to a payer directory.",
    submit: "Records the payer submission reference and server timestamp. It does not send a payer update.",
    verify: "Records the observed payer value and evidence note. The API compares it with the active approved proposal and may reopen the case.",
  };
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const payload: RemediationTransitionInput = { action, actor, reason };
    if (action === "approve") payload.proposed_correction_value = proposal;
    if (action === "submit") payload.submission_reference = submissionReference;
    if (action === "verify") { payload.observed_payer_value = observedValue; payload.verification_evidence_note = verificationNote; }
    mutation.mutate(payload);
  };
  const requiresProposal = action === "approve";
  const requiresSubmission = action === "submit";
  const requiresVerification = action === "verify";
  const ready = actor.trim() && reason.trim() && (!requiresProposal || proposal.trim()) && (!requiresSubmission || submissionReference.trim()) && (!requiresVerification || (observedValue.trim() && verificationNote.trim()));
  return <section className="remediation-action-panel"><div className="section-title"><div><h3>Record a human workflow event</h3><p>{explanation[action]}</p></div></div><div className="action-pills" aria-label="Available case actions">{actions.map((next) => <button key={next} type="button" className={action === next ? "active" : ""} onClick={() => { setAction(next); setRecorded(false); }}>{pretty(next)}</button>)}</div><form onSubmit={submit}>
    <label>Actor <em>required</em><input aria-label="Remediation actor" value={actor} onChange={(event) => setActor(event.target.value)} placeholder="Name recorded with this event" required /></label>
    <label>Reason <em>required</em><textarea aria-label="Remediation reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why is this action appropriate?" rows={3} required /></label>
    {requiresProposal ? <label>Proposed correction <em>required</em><input aria-label="Proposed correction" value={proposal} onChange={(event) => setProposal(event.target.value)} placeholder="Human-approved value to verify" required /></label> : null}
    {requiresSubmission ? <label>Submission reference <em>required</em><input aria-label="Submission reference" value={submissionReference} onChange={(event) => setSubmissionReference(event.target.value)} placeholder="Payer ticket, portal, or correspondence reference" required /></label> : null}
    {requiresVerification ? <><label>Observed payer value <em>required</em><input aria-label="Observed payer value" value={observedValue} onChange={(event) => setObservedValue(event.target.value)} placeholder="Value currently visible in payer directory" required /></label><label>Verification evidence note <em>required</em><textarea aria-label="Verification evidence note" value={verificationNote} onChange={(event) => setVerificationNote(event.target.value)} placeholder="Where and when the value was observed" rows={3} required /></label></> : null}
    {mutation.isError ? <p className="form-error" role="alert">{mutation.error instanceof Error ? mutation.error.message : "The API rejected this transition. Refresh the case and try again."}</p> : null}
    {recorded ? <p className="form-success" role="status">Event recorded. The queue, case, and audit history were refreshed.</p> : null}
    <button className="button button-primary" disabled={!ready || mutation.isPending}>{mutation.isPending ? "Recording…" : `Record ${pretty(action)}`}</button>
  </form></section>;
}

function HistoryTimeline({ history }: { history: RemediationCaseDetail["history"] }) {
  return <section className="remediation-history"><h3>Append-only audit history</h3>{history.length === 0 ? <p className="muted">No workflow events have been recorded.</p> : <ol className="history">{history.map((event) => <li key={event.event_id} className={event.event_type === "reopen" ? "history-reopen" : ""}><div className="history-title"><b>{event.event_type === "reopen" ? "Verification failed — reopened" : pretty(event.event_type)}</b><span>{event.from_status ? `${pretty(event.from_status)} → ` : ""}{pretty(event.to_status)}</span></div><span>{event.reason}</span><small>Actor: {event.actor} · {timestamp(event.occurred_at)}</small>{event.proposed_correction_value ? <small><strong>Proposal recorded:</strong> {event.proposed_correction_value}{event.original_payer_value !== null ? ` · payer listed: ${event.original_payer_value}` : ""}{event.reference_value !== null ? ` · comparison: ${event.reference_value}` : ""}</small> : null}{event.submission_reference ? <small><strong>Submission:</strong> {event.submission_reference}{event.submitted_at ? ` · ${timestamp(event.submitted_at)}` : ""}</small> : null}{event.observed_payer_value ? <small><strong>Observed payer value:</strong> {event.observed_payer_value}</small> : null}{event.verification_evidence_note ? <small><strong>Verification evidence:</strong> {event.verification_evidence_note}</small> : null}</li>)}</ol>}</section>;
}
