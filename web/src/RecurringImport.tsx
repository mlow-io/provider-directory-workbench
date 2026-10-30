import { useEffect, useState } from "react";
import "./recurring-import.css";

type Cell = unknown;
type ChangeField = { field: string; old: Cell; new: Cell };
type ChangeStatus = "new" | "changed" | "unchanged" | "unresolved" | "blocked_invalid" | "missing";
type ChangeEntry = {
  key: string | null;
  status: ChangeStatus;
  old: Record<string, unknown> | null;
  new: Record<string, unknown> | null;
  fields: ChangeField[];
  previous_locator?: unknown;
  current_locator?: unknown;
  previous_receipt_id?: string | null;
  mapping_revision_id?: string | null;
  baseline_mapping_revision_id?: string | null;
  interpretation_changed?: boolean;
};
export type DeliveryComparison = {
  baseline?: { attempt_id: string; receipt_id: string; label: string; committed_at: string; mapping_revision_id?: string | null } | null;
  raw_row_count?: number;
  unique_identity_count?: number;
  new?: number;
  changed?: number;
  unchanged?: number;
  unresolved?: number;
  blocked_invalid?: number;
  missing_from_this_delivery?: number;
  entries?: ChangeEntry[];
  [key: string]: unknown;
};
type MappingRevision = {
  id: string;
  name: string;
  source: string;
  profile: string;
  scope: unknown;
  settings: Record<string, unknown>;
  required_headers: string[];
  actor: string;
  reason: string;
  created_at: string;
};
type Parsing = { sheet: string; header_row: number; encoding: string; delimiter: string };
const statuses: ChangeStatus[] = ["new", "changed", "unchanged", "missing", "blocked_invalid", "unresolved"];
const label = (value: string) => value.replaceAll("_", " ");
const show = (value: unknown): string => value === null || value === undefined ? "—" : typeof value === "string" ? value || '""' : JSON.stringify(value);

export function RecurringImport({ receiptId, state, attemptId, appliedRevisionId, comparison, effectiveMapping, parsing, busy, onRun, onChanged }: {
  receiptId: string;
  state: string;
  attemptId: string;
  appliedRevisionId: string | null;
  comparison?: DeliveryComparison;
  effectiveMapping: Record<string, string>;
  parsing: Parsing;
  busy: boolean;
  onRun: (path: string, body: unknown) => Promise<void>;
  onChanged: () => Promise<void>;
}) {
  const [revisions, setRevisions] = useState<MappingRevision[]>([]);
  const [selectedRevision, setSelectedRevision] = useState("");
  const [name, setName] = useState("");
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<ChangeStatus | "all">("all");
  const loadRevisions = async () => {
    const response = await fetch(`/api/intakes/${encodeURIComponent(receiptId)}/saved-mappings`);
    if (!response.ok) throw new Error(`Saved mappings could not load (${response.status})`);
    const data = await response.json() as { items?: MappingRevision[] };
    setRevisions(Array.isArray(data.items) ? data.items : []);
  };
  useEffect(() => {
    setSelectedRevision("");
    void loadRevisions().catch((e: Error) => setError(e.message));
  }, [receiptId]);
  const saveRevision = async () => {
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`/api/intakes/${encodeURIComponent(receiptId)}/saved-mappings`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, actor, reason, expected_attempt: attemptId }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: unknown };
        throw new Error(typeof body.detail === "string" ? body.detail : `Save failed (${response.status})`);
      }
      const saved = await response.json() as MappingRevision;
      if (saved.id) setSelectedRevision(saved.id);
      await loadRevisions();
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  const refreshComparison = () => {
    const body = appliedRevisionId
      ? { mapping_revision_id: appliedRevisionId }
      : { mapping: effectiveMapping, ...parsing };
    void onRun("mapping", body);
  };
  const visible = (comparison?.entries ?? []).filter((entry) => status === "all" || entry.status === status);
  return <section className="ri-section" aria-label="Recurring import review">
    <h4>Recurring import review</h4>
    <p className="iw-muted">A saved mapping is an immutable interpretation template. Saving or applying one only reprocesses this delivery; accepting valid rows is a separate reviewer decision below.</p>
    {error && <p className="iw-error" role="alert">{error}</p>}
    <p>Applied mapping revision: <strong>{appliedRevisionId ?? "None — manual mapping"}</strong></p>
    <div className="ri-controls">
      <label>Saved mapping revision
        <select value={selectedRevision} onChange={(event) => setSelectedRevision(event.target.value)}>
          <option value="">Choose a reviewed revision</option>
          {revisions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}
        </select>
      </label>
      <button type="button" disabled={busy || saving || !selectedRevision} onClick={() => void onRun("mapping", { mapping_revision_id: selectedRevision })}>Apply saved mapping and reprocess</button>
    </div>
    {selectedRevision && (() => {
      const item = revisions.find((revision) => revision.id === selectedRevision);
      return item ? <p className="iw-muted">Required headers: {item.required_headers.join(", ") || "None"}. Saved by {item.actor} on {item.created_at}. Review any header drift before acceptance.</p> : null;
    })()}
    <details>
      <summary>Save this validated mapping as a revision</summary>
      <p className="iw-muted">Available only after a valid mapped preview. The current mapping, parsing settings, source and scope are saved by the service.</p>
      <form className="iw-form" onSubmit={(event) => { event.preventDefault(); void saveRevision(); }}>
        <label>Revision name<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Mapping reviewer<input required value={actor} onChange={(event) => setActor(event.target.value)} /></label>
        <label>Mapping reason<input required value={reason} onChange={(event) => setReason(event.target.value)} /></label>
        <button disabled={busy || saving || state !== "preview_ready" || !attemptId || !name || !actor || !reason}>Save mapping revision (does not accept)</button>
      </form>
    </details>
    {comparison && <details className="ri-comparison">
      <summary>Comparison with prior source deliveries</summary>
      {comparison.baseline ? <p>Baseline: <strong>{comparison.baseline.label}</strong> · receipt {comparison.baseline.receipt_id} · accepted {comparison.baseline.committed_at} · attempt {comparison.baseline.attempt_id}</p> : <p>No prior accepted delivery for this source and scope. Review every prospective row as new or unresolved.</p>}
      <p>Raw rows: <strong>{comparison.raw_row_count ?? 0}</strong> · Unique identities: <strong>{comparison.unique_identity_count ?? 0}</strong></p>
      <ul className="ri-counts">
        {statuses.map((item) => <li key={item}>{label(item)}: <strong>{item === "missing" ? comparison.missing_from_this_delivery ?? 0 : comparison[item] ?? 0}</strong></li>)}
      </ul>
      <p className="iw-muted">Quarantined rows remain separate evidence. Missing means absent from this delivery, not terminated. The visible comparison is bounded to 50 entries; the evidence packet retains the full result.</p>
      <button type="button" disabled={busy || saving} onClick={refreshComparison}>Refresh comparison</button>
      <label className="ri-filter">Filter changes
        <select value={status} onChange={(event) => setStatus(event.target.value as ChangeStatus | "all")}>
          <option value="all">All statuses</option>
          {statuses.map((item) => <option key={item} value={item}>{label(item)}</option>)}
        </select>
      </label>
      {visible.length === 0 ? <p className="iw-muted">No visible entries for this status.</p> : <ul className="ri-entries">
        {visible.map((entry, index) => <li key={`${entry.key ?? "unresolved"}-${entry.status}-${index}`}>
          <details>
            <summary><strong>{label(entry.status)}</strong> · {entry.key ?? "Unresolved identity"} {entry.interpretation_changed ? "· interpretation changed" : ""}</summary>
            <p className="iw-muted">Prior locator: {show(entry.previous_locator)} · Current locator: {show(entry.current_locator)}</p>
            {entry.fields.length ? <table><thead><tr><th scope="col">Field</th><th scope="col">Prior accepted</th><th scope="col">Prospective</th></tr></thead><tbody>
              {entry.fields.map((field, fieldIndex) => <tr key={`${field.field}-${fieldIndex}`}><th scope="row">{label(field.field)}</th><td>{show(field.old)}</td><td>{show(field.new)}</td></tr>)}
            </tbody></table> : <p className="iw-muted">No field-level differences.</p>}
            {(entry.status === "unresolved" || entry.status === "blocked_invalid") && <p className="iw-muted">Inspect the original and quarantined row evidence before accepting.</p>}
          </details>
        </li>)}
      </ul>}
      <details open><summary>Raw comparison data</summary><pre className="iw-json">{JSON.stringify(comparison, null, 2)}</pre></details>
    </details>}
  </section>;
}
