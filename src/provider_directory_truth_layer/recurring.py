"""Reviewed immutable mapping revisions and single-delivery comparisons.

These helpers share the intake database; they never accept observations or update work.
"""
from __future__ import annotations

import json
from collections import Counter


MIGRATION_3 = '''
CREATE TABLE mapping_revision (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL, profile TEXT NOT NULL,
 scope TEXT NOT NULL, settings TEXT NOT NULL, required_headers TEXT NOT NULL,
 actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX mapping_source ON mapping_revision(source, profile);
CREATE TRIGGER attempt_spec_no_update BEFORE UPDATE OF spec, fingerprint, receipt_id ON attempt
 BEGIN SELECT RAISE(ABORT, 'Immutable attempt interpretation'); END;
CREATE TRIGGER mapping_revision_no_update BEFORE UPDATE ON mapping_revision
 BEGIN SELECT RAISE(ABORT, 'Immutable mapping revision'); END;
CREATE TRIGGER mapping_revision_no_delete BEFORE DELETE ON mapping_revision
 BEGIN SELECT RAISE(ABORT, 'Immutable mapping revision'); END;
'''

PARSING_FIELDS = {'mapping', 'sheet', 'header_row', 'encoding', 'delimiter', 'roster_kind', 'bindings', 'fixed_network_binding_id'}


def scope(receipt):
    metadata = receipt['metadata']
    return json.loads(metadata).get('scope') if isinstance(metadata, str) else metadata.get('scope')


def comparison_scope(receipt, spec):
    kind = spec.get('roster_kind','clinic')
    networks = sorted({row['target_id'] for row in spec.get('binding_snapshot',{}).values() if row['kind']=='network'}) if kind=='network' else []
    return [scope(receipt),kind,networks]


def latest_baseline(conn, receipt, spec=None):
    # A duplicate receipt points at an existing interpretation, not a new snapshot.
    rows = conn.execute('''SELECT a.*, r.label, r.source, r.profile, r.metadata
      FROM attempt a JOIN receipt r ON r.id=a.receipt_id
      WHERE a.state='committed' AND r.source=? AND r.profile=?
      ORDER BY a.committed_at DESC, a.id DESC''', (receipt['source'], receipt['profile']))
    return next((dict(row) for row in rows if comparison_scope(row,json.loads(row['spec'])) == comparison_scope(receipt,spec or {})), None)


def baseline_info(baseline):
    if not baseline:
        return None
    return {key: baseline[key] for key in ('receipt_id', 'label', 'committed_at')} | {
        'attempt_id': baseline['id'], 'mapping_revision_id': json.loads(baseline['spec']).get('mapping_revision_id')}


def identity(row):
    norm = row['normalized']
    # Native source keys are text, never a row position or display label.
    native = row.get('native_id')
    if 'participation' in norm:
        part=norm['participation']
        if not all([native,part.get('network_id'),part.get('provider_id'),part.get('location_id')]):return None
        return json.dumps([str(native),part['network_id'],part['provider_id'],part['location_id']],ensure_ascii=False)
    location = norm.get('location_id')
    if not native or not location:
        return None
    return json.dumps([str(native), str(location)], ensure_ascii=False)


def mark_duplicate_keys(rows):
    counts = Counter(identity(row) for row in rows if identity(row) is not None)
    for row in rows:
        key = identity(row)
        if key is not None and counts[key] > 1:
            row['problems'].append('Duplicate or conflicting source record/location key; review all copies')


def compare(conn, receipt, rows, spec, baseline):
    previous = {}
    if baseline:
        for old in conn.execute('SELECT * FROM observation WHERE attempt_id=? ORDER BY id', (baseline['id'],)):
            row = {'native_id': old['native_id'], 'normalized': json.loads(old['normalized'])}
            key = identity(row)
            if key:
                previous.setdefault(key, []).append({'normalized': row['normalized'], 'locator': old['locator']})
    counts = dict.fromkeys(['new', 'changed', 'unchanged', 'unresolved', 'blocked_invalid'], 0)
    entries, present = [], set()
    baseline_revision = json.loads(baseline['spec']).get('mapping_revision_id') if baseline else None

    def entry(key, status, old, incoming, previous_locator, current_locator):
        old_values, new_values = old or {}, incoming or {}
        fields = [{'field': field, 'old': old_values.get(field), 'new': new_values.get(field),
                   'old_present': field in old_values, 'new_present': field in new_values}
                  for field in sorted(set(old_values) | set(new_values))
                  if field != 'participation' and (old_values.get(field) != new_values.get(field) or (field in old_values) != (field in new_values))]
        return {'key': key, 'status': status, 'old': old, 'new': incoming, 'fields': fields,
                'previous_locator': previous_locator, 'current_locator': current_locator,
                'previous_receipt_id': baseline['receipt_id'] if baseline else None,
                'mapping_revision_id': spec.get('mapping_revision_id'), 'baseline_mapping_revision_id': baseline_revision,
                'interpretation_changed': bool(baseline and {k:v for k,v in json.loads(baseline['spec']).items() if k != 'baseline_attempt_id'} != {k:v for k,v in spec.items() if k != 'baseline_attempt_id'})}

    for row in rows:
        key = identity(row)
        old_rows = previous.get(key, [])
        old = old_rows[0] if len(old_rows) == 1 else None
        if key is not None:
            present.add(key)
        if len(old_rows) > 1:
            row['problems'].append('Accepted baseline has ambiguous source identity; no value chosen')
        if key is None:
            status = 'unresolved'
        elif row['problems']:
            status = 'blocked_invalid'
        elif not old:
            status = 'new'
        else:
            status = 'unchanged' if old['normalized'] == row['normalized'] else 'changed'
        row['comparison'] = status
        counts[status] += 1
        entries.append(entry(key, status, old['normalized'] if old else None, row['normalized'],
                             old['locator'] if old else None, row['locator']))
    for key in sorted(set(previous) - present):
        old_rows = previous[key]
        old = old_rows[0] if len(old_rows) == 1 else None
        entries.append(entry(key, 'missing', old['normalized'] if old else None, None,
                             old['locator'] if old else None, None))
    return {**counts, 'baseline': baseline_info(baseline), 'raw_row_count': len(rows),
            'unique_identity_count': len(present), 'missing_from_this_delivery': len(set(previous) - present),
            'entries': entries, 'absence_meaning': 'Missing is review evidence only; never termination or removal'}
