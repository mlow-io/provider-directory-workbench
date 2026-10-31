-- SQLite 3 with JSON1; one row per source-native identity in either selected accepted delivery.
-- Parameters: :left_attempt and :right_attempt are validated committed observation-bearing IDs.
-- Key = native_id + normalized.location_id within equal source/profile/metadata.scope.
-- Unresolved native IDs and duplicate keys are rejected by the runner, not silently matched.
WITH left_rows AS (
  SELECT o.native_id, coalesce(cast(json_extract(o.normalized, '$.location_id') AS text), '') AS location_key,
         o.id AS observation_id, o.locator, o.normalized
  FROM observation AS o WHERE o.attempt_id = :left_attempt
), right_rows AS (
  SELECT o.native_id, coalesce(cast(json_extract(o.normalized, '$.location_id') AS text), '') AS location_key,
         o.id AS observation_id, o.locator, o.normalized
  FROM observation AS o WHERE o.attempt_id = :right_attempt
), all_keys AS (
  SELECT native_id, location_key FROM left_rows
  UNION SELECT native_id, location_key FROM right_rows
)
SELECT k.native_id, k.location_key,
       CASE WHEN l.observation_id IS NULL THEN 'new'
            WHEN r.observation_id IS NULL THEN 'missing_from_right'
            WHEN json(l.normalized) = json(r.normalized) THEN 'unchanged'
            ELSE 'changed' END AS difference,
       l.observation_id AS left_observation_id, l.locator AS left_locator,
       l.normalized AS left_normalized,
       r.observation_id AS right_observation_id, r.locator AS right_locator,
       r.normalized AS right_normalized
FROM all_keys AS k
LEFT JOIN left_rows AS l ON l.native_id = k.native_id AND l.location_key = k.location_key
LEFT JOIN right_rows AS r ON r.native_id = k.native_id AND r.location_key = k.location_key
ORDER BY k.native_id, k.location_key;
