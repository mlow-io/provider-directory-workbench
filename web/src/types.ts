export type CaseStatus = "new" | "assigned" | "in_review" | "resolved" | "deferred";
export type CaseAction = "assign" | "start_review" | "resolve" | "defer" | "add_note";

export interface BatchSummary {
  batch_id: string;
  source_label: string;
  record_count: number;
  exception_count: number;
  records_with_issues: number;
  issue_counts: Record<string, number>;
  severity_mix: Record<string, number>;
  source_summary: Record<string, number>;
  data_notice: string;
  limitations: string;
}

export interface ReviewCase {
  case_id: string;
  record_id: string;
  provider_name: string;
  issue_code: string;
  severity: string;
  field_name: string;
  source: string;
  review_status: CaseStatus;
  assigned_to: string | null;
  updated_at: string;
}

export interface CasePage { items: ReviewCase[]; total: number; }
export interface RecordValue { values: Record<string, string | number | null>; }
export interface HistoryEvent {
  event_id: number;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  assigned_to: string | null;
  reason: string;
  note: string | null;
  occurred_at: string;
}
export interface DuplicateComparison { candidate: RecordValue; records: RecordValue[]; warning: string; }
export interface CaseDetail {
  case: ReviewCase;
  exception: RecordValue;
  normalized_records: RecordValue[];
  recommendation: string;
  explanation: string;
  notes: string | null;
  history: HistoryEvent[];
  duplicate: DuplicateComparison | null;
}
export interface TransitionInput { action: CaseAction; assignee?: string; reason: string; note?: string; }

export type RemediationStatus = "new" | "triaged" | "approved" | "pending_verification" | "verified" | "reopened" | "deferred";
export type RemediationAction = "triage" | "approve" | "submit" | "verify" | "defer";

export interface RemediationCase {
  case_id: string;
  listing_id: string;
  reference_provider_key: string;
  field_name: string;
  status: RemediationStatus;
  risk_level: "high" | "medium" | "low";
  active_proposed_correction_value: string | null;
  updated_at: string;
}

export interface RemediationCasePage { items: RemediationCase[]; total: number; }
export interface PhaseOneEvidence { values: Record<string, string | number | boolean | null>; }
export interface RemediationEvent {
  event_id: number;
  case_id: string;
  event_type: string;
  from_status: RemediationStatus | null;
  to_status: RemediationStatus;
  actor: string;
  reason: string;
  proposed_correction_value: string | null;
  original_payer_value: string | null;
  reference_value: string | null;
  submission_reference: string | null;
  submitted_at: string | null;
  observed_payer_value: string | null;
  verification_evidence_note: string | null;
  occurred_at: string;
}

export interface RemediationCaseDetail {
  case: RemediationCase;
  evidence: PhaseOneEvidence;
  history: RemediationEvent[];
}

export interface RemediationTransitionInput {
  action: RemediationAction;
  actor: string;
  reason: string;
  proposed_correction_value?: string;
  submission_reference?: string;
  observed_payer_value?: string;
  verification_evidence_note?: string;
}
