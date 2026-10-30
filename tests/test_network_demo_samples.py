"""The three network demo files are stable, synthetic, and at participation-row grain."""

import csv
import hashlib
import io

from provider_directory_truth_layer.demo_samples import SAMPLES, generate, sample_payloads
from provider_directory_truth_layer.intake_store import IntakeStore


SOURCE = "synthetic-network-demo"
SCOPE = "synthetic-network-roster-v1"


def _rows(payload):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    return reader.fieldnames, list(reader)


def _receive(store, payload, filename):
    return store.receive(payload, filename, source=SOURCE, designation="synthetic", profile="flat",
                         metadata={"scope": SCOPE, "as_of": "2026-02-01", "completeness": "bounded"})


def _catalog_bindings(store):
    payer = store.create_catalog("organizations", {"label": "Synthetic Payer", "kind": "payer",
                                                  "actor": "demo", "reason": "Synthetic fixture"})
    clinic = store.create_catalog("organizations", {"label": "Synthetic Clinic", "kind": "clinic",
                                                   "actor": "demo", "reason": "Synthetic fixture"})
    targets = {"network": {
        code: store.create_catalog("networks", {"label": "Synthetic " + code,
                                                "payer_organization_id": payer["id"],
                                                "actor": "demo", "reason": "Synthetic fixture"})
        for code in ("CEDAR", "PINE")},
        "location": {
            code: store.create_catalog("locations", {"label": code, "organization_id": clinic["id"],
                                                 "actor": "demo", "reason": "Synthetic fixture"})
            for code in ("NORTH", "SOUTH")},
        "organization": {"CLINIC": clinic}}
    bindings = {}
    for kind, values in targets.items():
        bindings[kind] = {}
        for code, target in values.items():
            bindings[kind][code] = store.bind_source({"source": SOURCE, "kind": kind,
                                                       "source_key": code, "target_id": target["id"],
                                                       "actor": "demo", "reason": "Reviewed synthetic code"})["id"]
    return bindings


def test_network_payloads_are_deterministic_and_distinct_from_original_samples(tmp_path):
    original_ids = ["clinic-workbook", "clinic-csv", "clinic-changed", "nppes", "cms"]
    assert [item["id"] for item in SAMPLES[:5]] == original_ids
    assert [item["id"] for item in SAMPLES[5:]] == ["network-baseline", "network-changed", "network-header-drift"]
    assert all(item["label"].startswith("Synthetic") and item["profile"] == "flat" for item in SAMPLES[5:])
    assert all("mapping" in item["description"].lower() or "bindings" in item["description"].lower()
               for item in SAMPLES[5:])
    first = generate(tmp_path / "first")
    second = generate(tmp_path / "second")
    for sample in SAMPLES:
        assert (first / sample["filename"]).read_bytes() == (second / sample["filename"]).read_bytes()
    sample_payloads.cache_clear()
    cached = sample_payloads()
    sample_payloads.cache_clear()
    assert cached == sample_payloads()
    for sample in SAMPLES:
        assert cached[sample["id"]] == (first / sample["filename"]).read_bytes()
        assert hashlib.sha256(cached[sample["id"]]).hexdigest() == hashlib.sha256(
            (second / sample["filename"]).read_bytes()).hexdigest()


def test_network_rows_have_exact_grain_text_identifiers_and_header_drift():
    samples = sample_payloads()
    baseline_headers, baseline = _rows(samples["network-baseline"])
    changed_headers, changed = _rows(samples["network-changed"])
    drift_headers, drift = _rows(samples["network-header-drift"])
    assert len(baseline) == 3
    assert [(item["record_id"], item["network_code"], item["location_id"], item["phone"])
            for item in baseline] == [
        ("PART-001", "CEDAR", "NORTH", "6175550100"),
        ("PART-002", "CEDAR", "SOUTH", "6175550101"),
        ("PART-003", "PINE", "NORTH", "6175550100"),
    ]
    assert len(changed) == len(drift) == 5
    assert changed_headers != baseline_headers
    assert changed_headers[:3] == ["network_code", "location_id", "record_id"]
    assert "delivery_note" not in baseline_headers and "delivery_note" in changed_headers
    assert all(item["delivery_note"].startswith("Synthetic") for item in changed)
    assert [(item["record_id"], item["network_code"], item["location_id"]) for item in changed] == [
        ("PART-004", "PINE", "SOUTH"), ("PART-003", "PINE", "NORTH"),
        ("PART-001", "CEDAR", "NORTH"), ("PART-U", "UNKNOWN", "NORTH"),
        ("PART-003", "PINE", "NORTH"),
    ]
    assert {item["participation_status"] for item in changed if item["record_id"] == "PART-003"} == {
        "listed", "not_listed"}
    assert all(item["npi"] == "1234567890" and item["effective_date"] == "2026-01-01" and
               item["end_date"] == "" for item in baseline + changed)
    assert all(item["provider_name"] == "Synthetic Avery Example" and item["organization_label"] == "Synthetic Clinic"
               for item in baseline + changed)
    assert all(item["network_label"] == "Synthetic " + item["network_code"] for item in baseline + changed)
    assert all(item["address"] == ("1 Example Street" if item["location_id"] == "NORTH" else "2 Example Street")
               and item["zip"] == ("02108" if item["location_id"] == "NORTH" else "02109")
               for item in baseline + changed)
    assert "phone" in changed_headers and "phone" not in drift_headers
    assert "Published phone" in drift_headers
    assert [{("phone" if key == "Published phone" else key): value for key, value in item.items()}
            for item in drift] == changed


def test_network_samples_produce_declared_comparison_and_header_pause(tmp_path):
    samples = sample_payloads()
    store = IntakeStore(tmp_path / "intake.sqlite3", tmp_path / "runtime")
    bindings = _catalog_bindings(store)
    baseline = _receive(store, samples["network-baseline"], "synthetic-network-baseline.csv")
    baseline = store.mapping(baseline["id"], {"mapping": {header: header for header in _rows(samples["network-baseline"])[0]},
                                               "roster_kind": "network", "bindings": bindings})
    assert baseline["state"] == "preview_ready"
    revision = store.save_mapping(baseline["id"], {"name": "Synthetic network roster", "actor": "demo",
                                                   "reason": "Reviewed fixture mapping", "expected_attempt": baseline["attempt_id"]})
    baseline = store.commit(baseline["id"], {"actor": "demo", "reason": "Reviewed synthetic baseline",
                                                  "policy": "valid_rows", "expected_attempt": baseline["attempt_id"]})
    assert len(baseline["observations"]) == len(baseline["linked_cases"]) == 3
    changed = _receive(store, samples["network-changed"], "synthetic-network-changed.csv")
    changed = store.mapping(changed["id"], {"mapping_revision_id": revision["id"]})
    assert changed["state"] == "preview_ready"
    assert changed["preview"]["valid_count"] == 2
    assert changed["preview"]["quarantined_count"] == 3
    assert changed["preview"]["rows"][0]["original"]["delivery_note"].startswith("Synthetic")
    comparison = changed["preview"]["comparison"]
    assert comparison["baseline"]["attempt_id"] == baseline["attempt_id"]
    assert {field: comparison[field] for field in ("raw_row_count", "new", "changed", "blocked_invalid",
                                                    "unresolved", "missing_from_this_delivery")} == {
        "raw_row_count": 5, "new": 1, "changed": 1, "blocked_invalid": 2,
        "unresolved": 1, "missing_from_this_delivery": 1,
    }
    drift = _receive(store, samples["network-header-drift"], "synthetic-network-header-drift.csv")
    drift = store.mapping(drift["id"], {"mapping_revision_id": revision["id"]})
    assert drift["state"] == "needs_mapping"
    assert "phone" in drift["preview"]["error"].lower()
    assert "Published phone" in drift["preview"]["headers"]
