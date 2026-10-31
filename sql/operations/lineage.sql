-- SQLite 3; one row per linked observation for :case_id, retaining receipt and source row locator.
-- Parameters: :case_id (exact work_case.id). No work_evidence gives one case row with null lineage.
SELECT c.id AS case_id, c.status, c.evidence AS initial_evidence,
       o.id AS observation_id, o.locator, o.native_id, o.original, o.normalized,
       a.id AS attempt_id, a.state AS attempt_state, r.id AS receipt_id,
       r.label AS receipt_label, r.source, r.profile, r.artifact_sha,
       r.received_at
FROM work_case AS c
LEFT JOIN work_evidence AS we ON we.case_id = c.id
LEFT JOIN observation AS o ON o.id = we.observation_id
LEFT JOIN attempt AS a ON a.id = o.attempt_id
LEFT JOIN receipt AS r ON r.id = a.receipt_id
WHERE c.id = :case_id
ORDER BY r.received_at, r.id, o.locator, o.id;
