-- SQLite 3.25+; one row per work_case, including cases with no event.
-- Parameters: none. Equal timestamps break by highest integer work_event.id.
WITH ranked AS (
  SELECT e.*, row_number() OVER (
    PARTITION BY e.case_id ORDER BY e.occurred_at DESC, e.id DESC
  ) AS rank_in_case
  FROM work_event AS e
)
SELECT c.id AS case_id, c.status AS current_status, e.id AS event_id,
       e.action, e.actor, e.reason, e.from_status, e.to_status, e.occurred_at
FROM work_case AS c
LEFT JOIN ranked AS e ON e.case_id = c.id AND e.rank_in_case = 1
ORDER BY c.id;
