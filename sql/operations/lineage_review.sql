-- SQLite 3; one source-comparison evidence row for :case_id (schema v4 and later).
-- Complements accepted-observation lineage; invalid rows are never labeled accepted observations.
-- Parameters: :case_id exact work_case.id. No joins to work_event, so no event fan-out.
SELECT c.id AS case_id,c.status,c.evidence AS initial_evidence,NULL AS observation_id,
       e.locator,NULL AS native_id,e.payload AS original,NULL AS normalized,
       a.id AS attempt_id,a.state AS attempt_state,r.id AS receipt_id,r.label AS receipt_label,
       r.source,r.profile,r.artifact_sha,r.received_at,e.status AS comparison_status
FROM participation_review_evidence e JOIN work_case c ON c.id=e.case_id
JOIN attempt a ON a.id=e.attempt_id JOIN receipt r ON r.id=a.receipt_id
WHERE e.case_id=:case_id AND e.status IN ('missing','blocked_invalid')
ORDER BY r.received_at,r.id,e.id;
