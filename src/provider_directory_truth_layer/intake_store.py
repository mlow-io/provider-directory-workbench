"""Durable bounded intake service. Artifacts are bytes; receipts are deliveries.

The service deliberately uses explicit mapping and operator-confirmed location links.
It never infers that a bounded source's absence terminates a provider.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .storage import connect, database_path, storage_root
from .normalize import normalize_phone

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20_000
FIELDS = ['record_id', 'npi', 'provider_name', 'address', 'city', 'state', 'zip', 'phone', 'location_id', 'listing_id', 'reference_phone', 'specialty', 'status', 'source_updated_at']
REQUIRED = ['npi', 'provider_name', 'address', 'city', 'state', 'zip', 'phone']
VERSION = 4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return uuid.uuid4().hex


def packed(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(packed(value).encode()).hexdigest()


class Conflict(ValueError):
    pass


SCHEMA = [
    '''create table artifact (sha text primary key, size integer not null, storage_key text not null);
    create table receipt (id text primary key, label text not null, source text not null,
      designation text not null, received_at text not null, artifact_sha text references artifact(sha),
      profile text not null, duplicate_of text references receipt(id), metadata text not null);
    create table attempt (id text primary key, receipt_id text not null references receipt(id),
      spec text not null, fingerprint text not null, state text not null, preview text not null,
      created_at text not null, committed_at text, decision text);
    create index attempt_fingerprint on attempt(fingerprint);
    create table observation (id text primary key, attempt_id text not null references attempt(id),
      native_id text, locator text not null, original text not null, normalized text not null,
      provider_id text, location_id text, source_updated_at text, retrieved_at text not null,
      human_verified_at text);
    create table relationship (id integer primary key, observation_id text not null references observation(id),
      provider_id text not null, location_id text not null, actor text not null, reason text not null, occurred_at text not null);
    create table work_case (id text primary key, kind text not null, identity_key text unique,
      provider_name text not null, location_id text, field_name text not null, issue text not null,
      risk_level text not null, risk_reason text not null, status text not null,
      owner text, follow_up text, version integer not null default 0, evidence text not null,
      proposal text, observed text, created_at text not null, updated_at text not null);
    create table work_evidence (case_id text references work_case(id), observation_id text references observation(id),
      primary key(case_id, observation_id));
    create table work_event (id integer primary key, case_id text not null references work_case(id),
      action text not null, actor text not null, reason text not null, payload text not null,
      from_status text not null, to_status text not null, occurred_at text not null);
    create trigger work_event_no_update before update on work_event begin select raise(abort,'Append-only events'); end;
    create trigger work_event_no_delete before delete on work_event begin select raise(abort,'Append-only events'); end;
    create table schema_migration (version integer primary key, applied_at text not null);
    '''
]


class IntakeStore:
    def __init__(self, path: Path | None = None, root: Path | None = None):
        self.path = path or database_path()
        self.root = root or storage_root()
        self.artifacts = self.root / 'artifacts'
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.migrate()
        self.reconcile_artifacts()

    def reconcile_artifacts(self):
        # Staged/orphan bytes are retained for inspection, never mistaken for accepted data.
        with self.db() as conn:
            known = {r[0] for r in conn.execute('select storage_key from artifact')}
        present = {p.name for p in self.artifacts.iterdir() if p.is_file()}
        report = {'checked_at': now(), 'staged': sorted(k for k in present if k.endswith('.staged')),
                  'unregistered': sorted(k for k in present-known if not k.endswith('.staged')),
                  'missing_registered': sorted(known-present), 'policy': 'Retained for inspection; never auto-delete or accept'}
        (self.root / 'artifact-recovery.json').write_text(packed(report))
        return report

    def db(self):
        return connect(self.path)

    def migrate(self):
        with self.db() as conn:
            version = conn.execute('pragma user_version').fetchone()[0]
            if version > VERSION:
                raise ValueError(f'Unsupported future schema {version}; supported {VERSION}')
            if version == 0:
                # Back up before adding anything to a legacy database. Never fabricate old originals.
                tables = conn.execute("select name from sqlite_master where type='table'").fetchall()
                if tables:
                    backup = self.path.with_name(self.path.name + '.pre-intake-v1.bak')
                    if not backup.exists():
                        with closing(sqlite3.connect(backup)) as target:
                            conn.backup(target)
                conn.executescript('BEGIN IMMEDIATE;\n' + SCHEMA[0] + "\ninsert into schema_migration values (1, datetime('now'));\npragma user_version=1;\nCOMMIT;")
            if version < 2:
                if version == 1:
                    backup = self.path.with_name(self.path.name + '.pre-intake-v2.bak')
                    if not backup.exists():
                        with closing(sqlite3.connect(backup)) as target:
                            conn.backup(target)
                conn.executescript("BEGIN IMMEDIATE; ALTER TABLE relationship ADD COLUMN location_index integer; INSERT INTO schema_migration VALUES (2, datetime('now')); PRAGMA user_version=2; COMMIT;")
            if version < 3:
                from .recurring import MIGRATION_3
                if version >= 1:
                    backup = self.path.with_name(self.path.name + '.pre-intake-v3.bak')
                    if not backup.exists():
                        with closing(sqlite3.connect(backup)) as target:
                            conn.backup(target)
                conn.executescript("BEGIN IMMEDIATE;\n" + MIGRATION_3 + "\nINSERT INTO schema_migration VALUES (3, datetime('now')); PRAGMA user_version=3; COMMIT;")
            if version < 4:
                from .network_store import MIGRATION_4
                if version >= 1:
                    backup = self.path.with_name(self.path.name + '.pre-intake-v4.bak')
                    if not backup.exists():
                        with closing(sqlite3.connect(backup)) as target:
                            conn.backup(target)
                conn.executescript("BEGIN IMMEDIATE;\n" + MIGRATION_4 + "\nINSERT INTO schema_migration VALUES (4, datetime('now')); PRAGMA user_version=4; COMMIT;")
            # A killed process can leave a processing marker, but no partial committed batch.
            conn.execute("update attempt set state='interrupted' where state='processing'")

    def retain(self, payload: bytes) -> str:
        if not payload or len(payload) > MAX_BYTES:
            raise ValueError('Artifact must contain 1 byte to 10 MiB')
        sha = hashlib.sha256(payload).hexdigest()
        dest = self.artifacts / sha
        if not dest.exists():
            stage = self.artifacts / (sha + '.' + uid() + '.staged')
            with stage.open('xb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(stage, dest)
        with self.db() as conn:
            conn.execute('insert or ignore into artifact values (?,?,?)', (sha, len(payload), sha))
        return sha

    def receive(self, payload: bytes, filename: str, source='clinic', designation='synthetic', profile='flat', metadata=None):
        if designation not in {'synthetic', 'public', 'local'}:
            raise ValueError('Choose synthetic, public, or local designation')
        if profile not in {'flat', 'nppes', 'cms'}:
            raise ValueError('Supported JSON profiles: flat, nppes, cms')
        if not source.strip():
            raise ValueError('A source namespace/scope is required')
        source = source.strip()
        metadata = metadata or {}
        sha = self.retain(payload)
        receipt_id = uid()
        with self.db() as conn:
            candidates = conn.execute('SELECT id,metadata FROM receipt WHERE artifact_sha=? AND source=? AND profile=? ORDER BY received_at,id',(sha,source,profile))
            duplicate = next((row for row in candidates if json.loads(row['metadata']).get('scope') == metadata.get('scope')),None)
            conn.execute('insert into receipt values (?,?,?,?,?,?,?,?,?)', (receipt_id, Path(filename).name, source.strip(), designation, now(), sha, profile, duplicate[0] if duplicate else None, packed(metadata or {})))
        with self.db() as conn:
            candidates = conn.execute("SELECT a.spec,r.metadata FROM attempt a JOIN receipt r ON r.id=a.receipt_id WHERE r.artifact_sha=? AND r.source=? AND r.profile=? AND a.state='committed' ORDER BY a.committed_at DESC,a.id DESC",(sha,source,profile))
            prior = next((row for row in candidates if json.loads(row['metadata']).get('scope') == metadata.get('scope')),None)
        settings = {k:v for k,v in json.loads(prior[0]).items() if k not in {'adapter_version','profile','baseline_attempt_id'}} if prior else {}
        if settings.get('mapping_revision_id'):
            settings = {'mapping_revision_id': settings['mapping_revision_id']}
        self.mapping(receipt_id, settings)
        return self.detail(receipt_id)

    def rows(self, receipt: dict, spec: dict):
        path = self.artifacts / receipt['artifact_sha']
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != receipt['artifact_sha']:
            raise ValueError('Retained artifact digest mismatch')
        label = receipt['label'].lower()
        if label.endswith('.json') or receipt['profile'] != 'flat':
            from .intake_adapters import parse_json
            rows = parse_json(payload, receipt['profile'])
            if len(rows) > MAX_ROWS:
                raise ValueError('Row limit is 20,000; split the artifact')
            return rows, [], [], True
        if label.endswith('.xlsx'):
            # Reject expanded zip bombs before openpyxl inflates XML.
            import zipfile
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if sum(x.file_size for x in archive.infolist()) > 100 * MAX_BYTES:
                    raise ValueError('Workbook expanded size exceeds 1 GiB')
            workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=False)
            sheets = workbook.sheetnames
            sheet = spec.get('sheet') or sheets[0]
            if sheet not in sheets:
                workbook.close()
                raise ValueError('Select a worksheet from the retained workbook')
            header_row = int(spec.get('header_row', 1))
            if header_row < 1 or header_row > 100:
                raise ValueError('Header row must be between 1 and 100')
            worksheet = workbook[sheet]
            iterator = worksheet.iter_rows(min_row=header_row)
            header_cells = next(iterator, ())
            headers = [str(c.value or '').strip() for c in header_cells]
            rows = []
            for rowno, cells in enumerate(iterator, start=header_row + 1):
                if all(c.value is None for c in cells):
                    continue
                formulas = [c.coordinate for c in cells if c.data_type == 'f']
                values = [format(int(c.value), '0' + str(len(c.number_format)) + 'd') if isinstance(c.value, (int,float)) and re.fullmatch(r'0+', c.number_format) else str(c.value) if c.value is not None else '' for c in cells]
                original = dict(zip(headers, values))
                original['_cells'] = [{'cell': c.coordinate, 'type': c.data_type, 'number_format': c.number_format, 'value': str(c.value) if c.value is not None else None} for c in cells]
                rows.append({'original': original, 'locator': f'{sheet}!{rowno}', 'problems': [f'Formula cells are not executed: {", ".join(formulas)}'] if formulas else []})
                if len(rows) > MAX_ROWS:
                    workbook.close()
                    raise ValueError('Row limit is 20,000; split the artifact')
            workbook.close()
            return rows, headers, sheets, False
        if not label.endswith('.csv'):
            raise ValueError('Supported files: CSV, XLSX, or explicit-profile JSON')
        encoding = spec.get('encoding', 'utf-8-sig')
        if encoding not in {'utf-8-sig', 'utf-8', 'cp1252'}:
            raise ValueError('Supported encodings: utf-8-sig, utf-8, cp1252')
        delimiter = spec.get('delimiter', ',')
        if delimiter not in {',', ';', '\t', '|'}:
            raise ValueError('Choose comma, semicolon, tab, or pipe delimiter')
        reader = csv.DictReader(io.StringIO(payload.decode(encoding)), delimiter=delimiter)
        headers = reader.fieldnames or []
        rows = []
        for index, row in enumerate(reader, 2):
            problems = ['Row has more cells than headers'] if None in row else []
            row.pop(None, None)
            rows.append({'original': row, 'locator': f'row:{index}', 'problems': problems})
            if len(rows) > MAX_ROWS:
                raise ValueError('Row limit is 20,000; split the artifact')
        return rows, headers, [], False

    def catalog(self):
        from .network_store import catalog
        with self.db() as conn:
            return catalog(conn)

    def create_catalog(self, kind, payload):
        from .network_store import create_catalog
        return create_catalog(self, kind, payload)

    def bind_source(self, payload):
        from .network_store import bind_source
        return bind_source(self, payload)

    def saved_mappings(self, receipt_id):
        from .recurring import scope
        with self.db() as conn:
            receipt = self._receipt(conn, receipt_id)
            items = [dict(row) for row in conn.execute(
                'SELECT * FROM mapping_revision WHERE source=? AND profile=? ORDER BY created_at DESC,id DESC',
                (receipt['source'], receipt['profile'])) if json.loads(row['scope']) == scope(receipt)]
        for row in items:
            for key in ('scope', 'settings', 'required_headers'):
                row[key] = json.loads(row[key])
        return {'items': items}

    def save_mapping(self, receipt_id, payload):
        from .recurring import PARSING_FIELDS, scope
        actor, reason, name = (self.required(payload, key) for key in ('actor', 'reason', 'name'))
        with self.db() as conn:
            conn.execute('begin immediate')
            receipt = self._receipt(conn, receipt_id)
            attempt = conn.execute('SELECT * FROM attempt WHERE receipt_id=? ORDER BY created_at DESC,id DESC LIMIT 1', (receipt_id,)).fetchone()
            if attempt is None or payload.get('expected_attempt') != attempt['id']:
                raise Conflict('Interpretation changed; review the current preview before saving a mapping')
            preview, spec = json.loads(attempt['preview']), json.loads(attempt['spec'])
            if attempt['state'] not in {'preview_ready', 'committed', 'duplicate_delivery'} or not preview.get('headers'):
                raise ValueError('A ready tabular mapped preview is required before saving')
            settings = {key: value for key, value in spec.items() if key in PARSING_FIELDS}
            settings['mapping'] = preview['mapping']
            revision = {'id': uid(), 'name': name, 'source': receipt['source'], 'profile': receipt['profile'],
                        'scope': scope(receipt), 'settings': settings,
                        'required_headers': sorted(set(preview['mapping'].values())),
                        'actor': actor, 'reason': reason, 'created_at': now()}
            conn.execute('INSERT INTO mapping_revision VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (revision['id'], name, receipt['source'], receipt['profile'], packed(revision['scope']),
                          packed(settings), packed(revision['required_headers']), actor, reason, revision['created_at']))
        return revision

    def mapping(self, receipt_id: str, settings: dict):
        from .recurring import scope, latest_baseline
        from .network_store import binding_snapshot
        settings = dict(settings)
        settings.pop('binding_snapshot', None)
        settings.pop('baseline_attempt_id', None)  # Baselines are always pinned by the service.
        required_headers = []
        with self.db() as conn:
            receipt = self._receipt(conn, receipt_id)
            if settings.get('mapping_revision_id'):
                revision_id = settings['mapping_revision_id']
                # Revision settings are immutable: changing columns requires a new revision.
                if set(settings) - {'mapping_revision_id', 'adapter_version', 'profile'}:
                    raise ValueError('Saved mapping settings cannot be overridden; review a new revision')
                revision = conn.execute('SELECT * FROM mapping_revision WHERE id=?', (revision_id,)).fetchone()
                if revision is None:
                    raise KeyError('Mapping revision not found')
                if (revision['source'], revision['profile'], json.loads(revision['scope'])) != (receipt['source'], receipt['profile'], scope(receipt)):
                    raise ValueError('Mapping revision has incompatible source, profile or scope')
                required_headers = json.loads(revision['required_headers'])
                settings = {**json.loads(revision['settings']), 'mapping_revision_id': revision_id}
            recurring = receipt['profile'] == 'flat' and receipt['label'].lower().endswith(('.csv', '.xlsx'))
            snapshot = binding_snapshot(conn, receipt, settings)
            resolved_settings = {**settings, 'binding_snapshot': snapshot} if settings.get('roster_kind') == 'network' else settings
            baseline = latest_baseline(conn, receipt, resolved_settings) if recurring else None
        spec = {**resolved_settings, 'adapter_version': '1', 'profile': receipt['profile']}
        if recurring:
            spec['baseline_attempt_id'] = baseline['id'] if baseline else None
        attempt_id = uid()
        fingerprint = digest([receipt['source'], json.loads(receipt['metadata']).get('scope'), receipt['artifact_sha'], {key: value for key, value in spec.items() if key != 'baseline_attempt_id'}])
        with self.db() as conn:
            conn.execute('insert into attempt values (?,?,?,?,?,?,?,?,?)', (attempt_id, receipt_id, packed(spec), fingerprint, 'processing', '{}', now(), None, None))
        try:
            rows, headers, sheets, native = self.rows(receipt, spec)
            if len(set(headers)) != len(headers) or any(not h for h in headers):
                raise ValueError('Headers must be nonblank and unique; choose another header row')
            from .network_store import NETWORK_FIELDS
            mapping = {k:v for k,v in settings.get('mapping', {}).items() if v} or {key: key for key in [*FIELDS, *NETWORK_FIELDS] if key in headers}
            missing = [] if native else [key for key in REQUIRED if key not in mapping]
            unknown = [value for value in mapping.values() if value not in headers] if not native else []
            missing_headers = sorted(set(required_headers) - set(headers))
            header_error = ('Required headers missing: ' + ', '.join(missing_headers)) if missing_headers else ('Mapped columns do not exist: ' + ', '.join(unknown)) if unknown else None
            for row in rows:
                original = row['original']
                normalized = row.get('normalized', {}) if native else {key: str(original.get(column) or '').strip() for key, column in mapping.items()}
                # JSON flat profiles may return scalar nullable values.
                normalized = {k: ('' if v is None else v) for k, v in normalized.items()}
                row['normalized'] = normalized
                row.setdefault('problems', [])
                if not native:
                    row['native_id'] = normalized.get('record_id') or None
                for field in REQUIRED:
                    if not normalized.get(field):
                        row['problems'].append(f'Missing {field}')
                npi = str(normalized.get('npi', ''))
                if npi and not re.fullmatch(r'\d{10}', npi):
                    row['problems'].append('NPI must contain ten digits')
                postal = str(normalized.get('zip', ''))
                if postal and not re.fullmatch(r'\d{5}(?:-?\d{4})?', postal):
                    row['problems'].append('ZIP must contain five digits or ZIP+4')
                phone = str(normalized.get('phone', ''))
                if phone and len(normalize_phone(phone)) != 10:
                    row['problems'].append('Phone must contain ten digits')
                normalized['phone'] = normalize_phone(phone)
                normalized['zip'] = str(normalized.get('zip', ''))
                normalized['state'] = str(normalized.get('state', '')).upper()
            from .network_store import interpret_rows
            interpret_rows(rows, spec)
            if recurring:
                from .recurring import mark_duplicate_keys, compare
                mark_duplicate_keys(rows)
                with self.db() as conn:
                    comparison = compare(conn, receipt, rows, spec, baseline)
            else:
                comparison = self.compare_delivery(receipt, rows)
            preview = {'comparison': comparison, 'headers': headers, 'sheets': sheets, 'mapping': mapping, 'rows': rows,
                       'valid_count': sum(not r['problems'] for r in rows), 'quarantined_count': sum(bool(r['problems']) for r in rows),
                       'total': len(rows), 'mapping_revision_id': spec.get('mapping_revision_id'),
                       'state': 'needs_mapping' if missing or header_error else 'preview_ready',
                       'error': ('Map required fields: ' + ', '.join(missing)) if missing else header_error}
            with self.db() as conn:
                prior = conn.execute("select id from attempt where fingerprint=? and state='committed' order by created_at limit 1", (fingerprint,)).fetchone()
                if prior:
                    preview['reuses_attempt'] = prior[0]
                conn.execute('update attempt set state=?,preview=? where id=?', (preview['state'], packed(preview), attempt_id))
        except Exception as exc:
            # Keep a failed receipt for visible correction/retry. No source data is committed.
            with self.db() as conn:
                conn.execute("update attempt set state='failed',preview=? where id=?", (packed({'state': 'failed', 'error': str(exc), 'rows': [], 'headers': [], 'sheets': [], 'mapping': {}, 'valid_count': 0, 'quarantined_count': 0, 'total': 0}), attempt_id))
        return self.detail(receipt_id)

    @staticmethod
    def _receipt(conn, receipt_id):
        row = conn.execute('select * from receipt where id=?', (receipt_id,)).fetchone()
        if row is None:
            raise KeyError('Receipt not found')
        return dict(row)

    def compare_delivery(self, receipt, rows):
        def key(row):
            norm = row['normalized']
            return (str(row.get('native_id')), str(norm.get('location_id') or '')) if row.get('native_id') else None
        previous = {}
        with self.db() as conn:
            old = conn.execute("select o.*, r.metadata as receipt_metadata from observation o join attempt a on a.id=o.attempt_id join receipt r on r.id=a.receipt_id where r.source=? order by o.retrieved_at", (receipt['source'],))
            for row in old:
                if json.loads(row['receipt_metadata']).get('scope') != json.loads(receipt['metadata']).get('scope'):
                    continue
                item = self.observation(dict(row))
                if key(item):
                    previous[key(item)] = item['normalized']
        current = set()
        counts = {'new': 0, 'changed': 0, 'unchanged': 0, 'unresolved': 0}
        for row in rows:
            native = key(row)
            if native is None:
                counts['unresolved'] += 1
                row['comparison'] = 'unresolved'
            else:
                current.add(native)
                status = 'new' if native not in previous else 'unchanged' if previous[native] == row['normalized'] else 'changed'
                counts[status] += 1
                row['comparison'] = status
        counts['missing_from_this_delivery'] = len(set(previous) - current)
        counts['absence_meaning'] = 'Bounded delivery only; absence does not imply termination or removal'
        return counts

    def detail(self, receipt_id):
        with self.db() as conn:
            receipt = self._receipt(conn, receipt_id)
            receipt['metadata'] = json.loads(receipt['metadata'])
            attempts = [dict(r) for r in conn.execute('select * from attempt where receipt_id=? order by created_at,id', (receipt_id,))]
            for attempt in attempts:
                attempt['spec'] = json.loads(attempt['spec'])
                attempt['preview'] = json.loads(attempt['preview'])
            receipt['attempts'] = attempts
            receipt['preview'] = attempts[-1]['preview'] if attempts else None
            receipt['state'] = attempts[-1]['state'] if attempts else ('failed' if receipt['metadata'].get('error') else 'reference_only')
            receipt['attempt_id'] = attempts[-1]['id'] if attempts else None
            attempt_id = receipt['attempt_id']
            if receipt['preview'] and receipt['preview'].get('reuses_attempt'):
                attempt_id = receipt['preview']['reuses_attempt']
            receipt['observations'] = [self.observation(dict(r)) for r in conn.execute('select * from observation where attempt_id=?', (attempt_id,))]
            for observation in receipt['observations']:
                observation['relationships'] = [dict(r) for r in conn.execute('select * from relationship where observation_id=? order by id', (observation['id'],))]
            receipt['linked_cases'] = [dict(r) for r in conn.execute('''SELECT DISTINCT c.* FROM work_case c WHERE c.id IN
                (SELECT w.case_id FROM work_evidence w JOIN observation o ON o.id=w.observation_id WHERE o.attempt_id=?
                 UNION SELECT e.case_id FROM participation_review_evidence e WHERE e.attempt_id=?)''', (attempt_id,attempt_id))]
            return receipt

    @staticmethod
    def observation(row):
        row['original'] = json.loads(row['original'])
        row['normalized'] = json.loads(row['normalized'])
        return row

    def inbox(self):
        with self.db() as conn:
            rows = conn.execute("""select r.*, a.id as attempt_id, a.state from receipt r
              left join attempt a on a.id=(select id from attempt where receipt_id=r.id order by created_at desc,id desc limit 1)
              order by r.received_at desc""")
            items = []
            for row in rows:
                item = dict(row)
                item['metadata'] = json.loads(item['metadata'])
                item['state'] = item['state'] or ('failed' if item['metadata'].get('error') else 'reference_only')
                items.append(item)
        return {'items': items}

    def commit(self, receipt_id, payload):
        actor = self.required(payload, 'actor')
        reason = self.required(payload, 'reason')
        policy = payload.get('policy')
        if policy not in {'valid_rows', 'reject'}:
            raise ValueError('Choose valid_rows or reject acceptance policy')
        with self.db() as conn:
            conn.execute('begin immediate')
            receipt = self._receipt(conn, receipt_id)
            attempt = dict(conn.execute('select * from attempt where receipt_id=? order by created_at desc,id desc limit 1', (receipt_id,)).fetchone())
            if payload.get('expected_attempt') is not None and payload['expected_attempt'] != attempt['id']:
                raise Conflict('Interpretation changed since preview; refresh before acceptance')
            if attempt['state'] in {'committed', 'duplicate_delivery', 'rejected'}:
                return self.detail(receipt_id)
            if attempt['state'] != 'preview_ready' and policy != 'reject':
                raise ValueError('A valid mapped preview is required before acceptance')
            preview = json.loads(attempt['preview'])
            spec = json.loads(attempt['spec'])
            if policy == 'valid_rows' and 'baseline_attempt_id' in spec:
                from .recurring import latest_baseline
                baseline = latest_baseline(conn, receipt, spec)
                if spec['baseline_attempt_id'] != (baseline['id'] if baseline else None):
                    raise Conflict('Accepted baseline changed since preview; refresh comparison and review before acceptance')
            previous = conn.execute("select id from attempt where fingerprint=? and state='committed' limit 1", (attempt['fingerprint'],)).fetchone()
            if policy == 'valid_rows' and spec.get('roster_kind') == 'network':
                from .network_store import check_bindings
                check_bindings(conn, spec['binding_snapshot'])
            state = 'rejected' if policy == 'reject' else 'committed'
            if previous and state == 'committed':
                state = 'duplicate_delivery'
                preview['reuses_attempt'] = previous[0]
            elif state == 'committed':
                explicit_empty = spec.get('roster_kind') == 'network' and preview['total'] == 0 and preview['comparison'].get('baseline') is not None and json.loads(receipt['metadata']).get('completeness') == 'full'
                if not preview['valid_count'] and not explicit_empty:
                    raise ValueError('No valid rows to accept; correct mapping or reject')
                for row in preview['rows']:
                    if row['problems']:
                        continue
                    observation_id = uid()
                    norm = row['normalized']
                    provider = 'NPI:' + str(norm['npi']) if re.fullmatch(r'\d{10}', str(norm.get('npi',''))) else None
                    # A supplied source location ID scopes evidence within its namespace, not across organizations.
                    location = receipt['source'] + ':' + str(norm['location_id']) if norm.get('location_id') else None
                    if spec.get('roster_kind') == 'network':
                        provider = norm['participation']['provider_id']
                        location = norm['participation']['location_id']
                    conn.execute('insert into observation values (?,?,?,?,?,?,?,?,?,?,?)', (observation_id, attempt['id'], row.get('native_id'), row['locator'], packed(row['original']), packed(norm), provider, location, row.get('source_updated_at') or norm.get('source_updated_at'), receipt['received_at'], None))
                    observation = {'id': observation_id, 'native_id': row.get('native_id'), 'locator': row['locator'], 'original': row['original'], 'normalized': norm, 'provider_id': provider, 'location_id': location}
                    if spec.get('roster_kind') == 'network':
                        from .network_store import link_participation
                        observation['attempt_id'] = attempt['id']
                        observation['comparison'] = row.get('comparison')
                        link_participation(self, conn, receipt, observation, spec)
                    else:
                        self.link_work(conn, receipt, observation)
            if state == 'committed':
                from .network_review import record_comparison_work
                record_comparison_work(self,conn,receipt,attempt,preview,spec)
            conn.execute('update attempt set state=?,preview=?,committed_at=?,decision=? where id=?', (state, packed(preview), now(), packed({'policy':policy,'actor':actor,'reason':reason}), attempt['id']))
        return self.detail(receipt_id)

    def link_work(self, conn, receipt, observation):
        norm = observation['normalized']
        provider, location = observation['provider_id'], observation['location_id']
        # Only source-native record + explicit source location provides stable operational scope.
        stable = [receipt['source'], provider, location, norm.get('listing_id') or observation['native_id']] if provider and location and (norm.get('listing_id') or observation['native_id']) else None
        findings = []
        existing_fields = set()
        if stable:
            # Later observations belong to existing work even after the issue disappears.
            # Evidence alone must never verify or close an operator's correction.
            for field in ['phone', 'record', 'location_id', 'record_id']:
                for kind in ['qa', 'correction']:
                    prior = conn.execute('select id from work_case where identity_key=?', (digest([stable, kind, field]),)).fetchone()
                    if prior:
                        conn.execute('insert or ignore into work_evidence values (?,?)', (prior[0], observation['id']))
                        existing_fields.add(field)
        if not location:
            findings.append(('qa', 'location_id', 'Location relationship needs review', 'medium', 'No explicit operating-location relationship'))
        if not observation['native_id']:
            findings.append(('qa', 'record_id', 'Source-native identity unresolved', 'medium', 'Row position is provenance, not identity'))
        if location and norm.get('reference_phone') and normalize_phone(str(norm['reference_phone'])) != norm.get('phone'):
            findings.append(('correction', 'phone', 'Location phone differs from submitted reference', 'high', 'Patients may be unable to contact this operating location'))
        if not findings and not existing_fields:
            findings.append(('qa', 'record', 'Review accepted source observation', 'low', 'Human source-evidence review'))
        for kind, field, issue, risk, risk_reason in findings:
            key = digest([stable, kind, field]) if stable else None
            case = conn.execute('select id from work_case where identity_key=?', (key,)).fetchone() if key else None
            case_id = case[0] if case else uid()
            evidence = {'original': observation['original'], 'normalized': norm, 'locator': observation['locator'], 'receipt_id': receipt['id'], 'observation_id': observation['id'], 'listing_value': norm.get(field), 'reference_value': norm.get('reference_' + field), 'source': receipt['source'], 'designation': receipt['designation'], 'provider_id': provider, 'location_id': location}
            if not case:
                conn.execute('insert into work_case values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (case_id, kind, key, str(norm.get('provider_name','')), location, field, issue, risk, risk_reason, 'new', None, None, 0, packed(evidence), None, None, now(), now()))
            conn.execute('insert or ignore into work_evidence values (?,?)', (case_id, observation['id']))

    def work(self, network_id=None, organization_id=None, location_id=None):
        where,parameters=[],[]
        for column,value in [('s.network_id',network_id),('s.organization_id',organization_id),('s.practice_location_id',location_id)]:
            if value is not None:where.append(column+'=?');parameters.append(value)
        condition=(' WHERE '+' AND '.join(where)) if where else ''
        with self.db() as conn:
            rows=[dict(row) for row in conn.execute("""SELECT c.*,s.network_id,n.label network_label,
                s.organization_id,o.label organization_label,s.practice_location_id,l.label location_label
                FROM work_case c LEFT JOIN case_scope s ON s.case_id=c.id
                LEFT JOIN network n ON n.id=s.network_id LEFT JOIN organization o ON o.id=s.organization_id
                LEFT JOIN practice_location l ON l.id=s.practice_location_id"""+condition+"""
                ORDER BY CASE c.risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                CASE WHEN c.follow_up < date('now') THEN 0 ELSE 1 END,c.created_at,c.id""",parameters)]
        for row in rows:row['source']=json.loads(row.pop('evidence'))['source']
        return {'items':rows}

    def case(self, case_id):
        with self.db() as conn:
            row = conn.execute('select * from work_case where id=?', (case_id,)).fetchone()
            if row is None:
                raise KeyError('Work case not found')
            case = dict(row)
            case['evidence'] = json.loads(case['evidence'])
            from .network_review import case_scope, review_evidence
            case['scope'] = case_scope(conn,case_id)
            case['participation_review'] = review_evidence(conn,case_id)
            case['history'] = [{**dict(r), 'payload': json.loads(r['payload'])} for r in conn.execute('select * from work_event where case_id=? order by id', (case_id,))]
            case['later_evidence'] = [self.observation(dict(r)) for r in conn.execute('select o.* from observation o join work_evidence w on w.observation_id=o.id where w.case_id=? and o.id != ? order by o.retrieved_at', (case_id, case['evidence']['observation_id']))]
            return case

    @staticmethod
    def required(payload, field):
        value = payload.get(field)
        if value is None or not str(value).strip():
            raise ValueError(field + ' is required')
        return str(value).strip()

    def event(self, case_id, payload):
        actor, reason = self.required(payload,'actor'), self.required(payload,'reason')
        with self.db() as conn:
            conn.execute('begin immediate')
            row = conn.execute('select * from work_case where id=?', (case_id,)).fetchone()
            if row is None:
                raise KeyError('Work case not found')
            case = dict(row)
            if payload.get('follow_up'):
                from datetime import date
                try:
                    date.fromisoformat(payload['follow_up'])
                except (TypeError, ValueError) as exc:
                    raise ValueError('Follow-up must use YYYY-MM-DD') from exc
            if payload.get('expected_version') != case['version']:
                raise Conflict('Case changed since it was opened. Refresh evidence; your draft is retained.')
            action, status = payload.get('action'), case['status']
            target = status
            proposal, observed = case['proposal'], case['observed']
            rules = {'triage': ({'new','reopened','deferred','needs_information'},'triaged'), 'approve': ({'triaged'},'approved'), 'submit': ({'approved'},'pending_verification'), 'verify': ({'pending_verification'},'verified'), 'defer': ({'new','triaged','reopened'},'deferred'), 'resolve': ({'new','triaged','needs_information'},'resolved')}
            if action in {'assign','needs_information'}:
                if action == 'assign':
                    self.required(payload,'owner')
                else:
                    target = 'needs_information'
            elif action in rules:
                allowed, target = rules[action]
                if status not in allowed:
                    raise Conflict(f'Cannot {action} a {status} case')
                if case['kind'] == 'qa' and action in {'approve','submit','verify'}:
                    raise ValueError('QA disposition is separate from correction verification')
                if case['kind'] == 'correction' and action == 'resolve':
                    raise ValueError('Correction requires observed verification')
                if action == 'approve':
                    proposal = self.required(payload,'proposal')
                    if len(normalize_phone(proposal)) != 10:
                        raise ValueError('Proposed phone must contain ten digits')
                if action == 'submit':
                    self.required(payload,'submission_reference')
                if action == 'verify':
                    observed = self.required(payload,'observed')
                    if len(normalize_phone(observed)) != 10:
                        raise ValueError('Observed phone must contain ten digits')
                    self.required(payload,'verification_note')
                    if normalize_phone(observed) != normalize_phone(proposal):
                        target = 'reopened'
            else:
                raise ValueError('Unsupported workflow action')
            conn.execute('update work_case set status=?,owner=?,follow_up=?,proposal=?,observed=?,version=version+1,updated_at=? where id=? and version=?', (target,payload.get('owner',case['owner']),payload.get('follow_up',case['follow_up']),proposal,observed,now(),case_id,case['version']))
            conn.execute('insert into work_event (case_id,action,actor,reason,payload,from_status,to_status,occurred_at) values (?,?,?,?,?,?,?,?)', (case_id,action,actor,reason,packed(payload),status,target,now()))
        return self.case(case_id)

    def relationship(self, payload):
        actor, reason = self.required(payload,'actor'), self.required(payload,'reason')
        provider, location = self.required(payload,'provider_id'), self.required(payload,'location_id')
        with self.db() as conn:
            conn.execute('begin immediate')
            row = conn.execute('select * from observation where id=?',(payload.get('observation_id'),)).fetchone()
            if row is None:
                raise KeyError('Observation not found')
            norm = json.loads(row['normalized'])
            if provider != 'NPI:' + str(norm.get('npi','')):
                raise ValueError('Provider relationship must use the exact observed NPI; ambiguous identity remains unresolved')
            locations = norm.get('locations', [])
            index = payload.get('location_index')
            if len(locations) > 1 and index is None:
                raise ValueError('Choose a native location index; a provider observation can contain several locations')
            if index is not None:
                if not isinstance(index, int) or index < 0 or index >= len(locations):
                    raise ValueError('Native location index is out of range')
                if locations[index].get('purpose') == 'MAILING':
                    raise ValueError('Mailing evidence cannot establish an operating location')
                norm = {**norm, **locations[index]}
            conn.execute('insert into relationship (observation_id,provider_id,location_id,actor,reason,occurred_at,location_index) values (?,?,?,?,?,?,?)',(row['id'],provider,location,actor,reason,now(),index))
            if len(locations) <= 1:
                conn.execute('update observation set provider_id=?,location_id=? where id=?',(provider,location,row['id']))
            receipt = dict(conn.execute('select r.* from receipt r join attempt a on a.receipt_id=r.id where a.id=?',(row['attempt_id'],)).fetchone())
            observation = self.observation(dict(row)); observation.update(provider_id=provider,location_id=location,normalized=norm)
            if index is not None:
                observation['locator'] += '.' + locations[index].get('source_path', f'locations[{index}]')
            self.link_work(conn,receipt,observation)
        return {'observation_id': row['id'], 'provider_id':provider,'location_id':location,'actor':actor,'reason':reason}

    def link(self, payload):
        from urllib.parse import urlparse
        url = self.required(payload,'url')
        if urlparse(url).scheme not in {'http','https'}:
            raise ValueError('Evidence links must use http or https')
        receipt_id = uid()
        with self.db() as conn:
            conn.execute('insert into receipt values (?,?,?,?,?,?,?,?,?)',(receipt_id,self.required(payload,'title'),self.required(payload,'source'),'local',now(),None,'flat',None,packed({**payload,'assertion':'User supplied, not fetched or verified'})))
        return self.detail(receipt_id)
