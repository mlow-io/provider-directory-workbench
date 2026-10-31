-- SQLite 3; one row per work_case needing assignment or overdue follow-up.
-- Parameters: :as_of (ISO YYYY-MM-DD local operator date), :include_closed (0 or 1).
-- Null owner means unassigned; a follow_up equal to as_of is due today, not overdue.
SELECT c.id AS case_id, c.status, c.owner, c.follow_up, c.risk_level,
       c.provider_name, c.field_name,
       CASE WHEN c.owner IS NULL OR trim(c.owner) = '' THEN 1 ELSE 0 END AS unassigned,
       CASE WHEN c.follow_up IS NOT NULL AND c.follow_up < :as_of THEN 1 ELSE 0 END AS overdue
FROM work_case AS c
WHERE (:include_closed = 1 OR c.status NOT IN ('verified', 'resolved'))
  AND ((c.owner IS NULL OR trim(c.owner) = '') OR (c.follow_up IS NOT NULL AND c.follow_up < :as_of))
ORDER BY overdue DESC, unassigned DESC, c.follow_up, c.id;
