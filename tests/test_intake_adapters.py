import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from provider_directory_truth_layer import intake_adapters as adapters

FIXTURES = Path(__file__).parent / 'fixtures/intake'


def test_nppes_preserves_native_identity_all_locations_taxonomies_and_unknown_fields():
    payload = (FIXTURES / 'nppes-synthetic.json').read_bytes()
    rows = adapters.parse_json(payload, 'nppes')
    assert rows[0]['native_id'] == '1000000001'
    assert rows[1]['native_id'] is None
    assert rows[1]['normalized']['status'] == 'unknown'
    assert len(rows[0]['normalized']['locations']) == 3
    assert len(rows[0]['normalized']['taxonomies']) == 2
    assert rows[0]['normalized']['zip'] == '012340001'
    assert rows[0]['original'] == json.loads(payload)['results'][0]
    assert rows[0]['source_updated_at'] == '2026-10-01'
    assert not rows[0]['normalized'].get('last_verified_date')
    assert rows[1]['locator'] == '$.results[1]'


def test_cms_native_enrollment_group_address_grain_and_missing_ids():
    rows = adapters.parse_json((FIXTURES / 'cms-synthetic.json').read_bytes(), 'cms')
    assert len(rows) == 3
    assert len({r['normalized']['npi'] for r in rows}) == 1
    assert rows[0]['native_id'] != rows[1]['native_id']
    assert rows[2]['native_id'] is None
    assert rows[0]['normalized']['zip'] == '01234'
    assert rows[0]['normalized']['provider_name'] == 'Synthetic Clinician'
    assert all(r['normalized']['status'] == 'unknown' for r in rows)


@pytest.mark.parametrize('profile,payload', [
    ('flat', b'{}'), ('flat', b'[1]'), ('flat', b'{broken'),
    ('flat', b'\xff'), ('wrong', b'[]'), ('nppes', b'{"results":[]}'),
    ('nppes', b'{"result_count":1,"results":[]}'),
    ('nppes', b'{"Errors":[{"description":"bad query"}]}'),
    ('cms', b'{"error":"timeout","results":[]}'), ('cms', b'{"data":[]}'),
    ('nppes', b'{"result_count":1,"results":[{"addresses":"wrong"}]}'),
])
def test_explicit_profiles_reject_malformed_and_error_envelopes(profile, payload):
    with pytest.raises(ValueError):
        adapters.parse_json(payload, profile)


def test_zero_results_are_distinct_from_errors():
    assert adapters.parse_json(b'{"result_count":0}', 'nppes') == []
    assert adapters.parse_json(b'{"count":0,"results":[]}', 'cms') == []


def test_flat_retains_source_fields_and_missing_ids():
    rows = adapters.parse_json(b'[{"zip":"00123","unknown":null}, {"id":"native"}]', 'flat')
    assert rows[0]['native_id'] is None
    assert rows[0]['normalized']['zip'] == '00123'
    assert rows[1]['native_id'] == 'native'


@pytest.mark.parametrize('query', [{'limit':201}, {'limit':0}, {'limit':'oops'}, {'skip':1001}, {'url':'https://localhost'}])
def test_fetch_refuses_invalid_or_unbounded_requests(query, monkeypatch):
    monkeypatch.setattr(adapters, '_read_url', lambda _: pytest.fail('network must not be reached'))
    with pytest.raises(ValueError):
        adapters.fetch_public('nppes', query)


def test_fetch_scope_cap_and_conservative_truncation(monkeypatch):
    monkeypatch.setattr(adapters, '_read_url', lambda _: b'{"result_count":1,"results":[{"number":"1000000001"}]}')
    fetched = adapters.fetch_public('nppes', {'limit':1, 'state':'TN'})
    assert fetched['metadata']['truncated'] is True
    assert fetched['metadata']['scope']['state'] == 'TN'
    assert 'version=2.1' in fetched['metadata']['request_url']
    assert len(fetched['metadata']['response_sha256']) == 64
    monkeypatch.setattr(adapters, '_read_url', lambda _: b'{"result_count":2,"results":[{},{}]}')
    with pytest.raises(ValueError, match='more records'):
        adapters.fetch_public('nppes', {'limit':1})


def test_cms_retains_dataset_metadata_and_query_scope(monkeypatch):
    seen = []
    def read(url):
        seen.append(url)
        if 'metastore' in url:
            return b'{"identifier":"mj5m-pzi6","modified":"2026-10-02","distribution":[{"mediaType":"text/csv"}]}'
        return b'{"count":10,"results":[{"NPI":"1000000001"}]}'
    monkeypatch.setattr(adapters, '_read_url', read)
    fetched = adapters.fetch_public('cms', {'limit':1, 'state':'TN'})
    assert fetched['metadata']['dataset_metadata']['modified'] == '2026-10-02'
    assert fetched['metadata']['truncated'] is True
    assert fetched['metadata']['total_matches'] == 10
    assert 'conditions%5B0%5D%5Bproperty%5D=state' in seen[-1]


class Response(io.BytesIO):
    pass


def test_transient_retry_respects_retry_after(monkeypatch):
    calls, sleeps = [], []
    class Opener:
        def open(self, request, timeout):
            calls.append(timeout)
            if len(calls) < 3:
                raise HTTPError(request.full_url, 429, 'busy', {'Retry-After':'2'}, io.BytesIO(b'busy'))
            return Response(b'{}')
    monkeypatch.setattr(adapters, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(adapters.time, 'sleep', sleeps.append)
    assert adapters._read_url(adapters.NPPES_URL) == b'{}'
    assert calls == [15, 15, 15]
    assert sleeps == [2, 2]


def test_long_retry_after_fails_without_shortening_server_delay(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 503, 'busy', {'Retry-After':'120'}, io.BytesIO(b'busy'))
    monkeypatch.setattr(adapters, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(adapters.time, 'sleep', lambda _: pytest.fail('must not retry early'))
    with pytest.raises(ValueError, match='retry later'):
        adapters._read_url(adapters.NPPES_URL)


def test_connection_failure_is_bounded_and_not_zero_matches(monkeypatch):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(1)
            raise URLError('timed out')
    monkeypatch.setattr(adapters, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(adapters.time, 'sleep', lambda _: None)
    with pytest.raises(ValueError, match='after 3 attempts'):
        adapters._read_url(adapters.NPPES_URL)
    assert len(calls) == 3


def test_response_size_cap(monkeypatch):
    monkeypatch.setattr(adapters, 'MAX_BYTES', 5)
    class Opener:
        def open(self, request, timeout):
            return Response(b'123456')
    monkeypatch.setattr(adapters, 'build_opener', lambda *args: Opener())
    with pytest.raises(ValueError, match='exceeds'):
        adapters._read_url(adapters.NPPES_URL)


@pytest.mark.parametrize('url', ['http://npiregistry.cms.hhs.gov/api/', 'https://localhost/', 'https://npiregistry.cms.hhs.gov:444/api/'])
def test_redirect_cannot_escape_owned_https_host(url):
    from urllib.request import Request
    with pytest.raises(ValueError, match='redirect'):
        adapters._OwnedRedirects().redirect_request(Request(adapters.NPPES_URL), None, 302, '', {}, url)


def test_cms_live_api_machine_names_match_dictionary_labels():
    # Observed CMS API columns use underscores and lowercase rather than labels.
    row = {"npi":"1000000001", "provider_first_name":"Synthetic",
           "provider_last_name":"Clinician", "citytown":"Example",
           "zip_code":"01234", "telephone_number":"5550100000"}
    normalized = adapters.parse_json(json.dumps({"results":[row]}).encode(), 'cms')[0]['normalized']
    assert normalized['provider_name'] == 'Synthetic Clinician'
    assert normalized['city'] == 'Example'
    assert normalized['zip'] == '01234'
    assert normalized['phone'] == '5550100000'


@pytest.mark.parametrize('body', [b'{"Errors":[{"description":"invalid NPI"}]}', b'{"unexpected":"schema"}', b'<html>upstream unavailable</html>'])
def test_invalid_success_envelope_retains_response_and_scope(monkeypatch, body):
    monkeypatch.setattr(adapters, '_read_url', lambda _: body)
    with pytest.raises(adapters.PublicFetchError) as caught:
        adapters.fetch_public('nppes', {'limit':1, 'state':'TN'})
    error = caught.value
    assert error.payload == body
    assert error.source == error.profile == 'nppes'
    assert error.label == 'NPPES public registry'
    assert error.metadata['scope']['state'] == 'TN'
    assert error.metadata['state'] == 'failed'
    assert error.metadata['request_url'].startswith(adapters.NPPES_URL)
    assert len(error.metadata['response_sha256']) == 64


def test_http_failure_retains_bounded_body_status_and_source(monkeypatch):
    monkeypatch.setattr(adapters, 'MAX_BYTES', 10)
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 403, 'forbidden', {}, io.BytesIO(b'{"error":"forbidden"}'))
    monkeypatch.setattr(adapters, 'build_opener', lambda *args: Opener())
    with pytest.raises(adapters.PublicFetchError, match='HTTP 403') as caught:
        adapters.fetch_public('nppes', {'limit':1})
    assert caught.value.payload == b'{"error":"'
    assert caught.value.metadata['http_status'] == 403
    assert caught.value.metadata['response_payload_truncated'] is True
    assert caught.value.source == 'nppes'


def test_cms_invalid_metadata_retains_metadata_response(monkeypatch):
    monkeypatch.setattr(adapters, '_read_url', lambda _: b'{"identifier":"unexpected"}')
    with pytest.raises(adapters.PublicFetchError, match='metadata schema') as caught:
        adapters.fetch_public('cms', {'limit':1})
    assert caught.value.payload == b'{"identifier":"unexpected"}'
    assert '/metastore/' in caught.value.metadata['request_url']
    assert caught.value.profile == 'cms'


def test_cms_datastore_failure_does_not_mislabel_metadata_as_error_body(monkeypatch):
    def read(url):
        if 'metastore' in url:
            return b'{"identifier":"mj5m-pzi6","distribution":[{}]}'
        raise adapters.PublicFetchError('connection failed', metadata={'request_url':url})
    monkeypatch.setattr(adapters, '_read_url', read)
    with pytest.raises(adapters.PublicFetchError) as caught:
        adapters.fetch_public('cms', {'limit':1})
    assert caught.value.payload is None
    assert '/datastore/' in caught.value.metadata['request_url']
    assert caught.value.metadata['dataset_metadata']['identifier'] == 'mj5m-pzi6'
