from provider_directory_truth_layer.npi_api import map_npi_record, npi_records_to_frame


def test_map_npi_record_uses_location_address_and_primary_taxonomy():
    record = {
        "number": "1234567890",
        "enumeration_type": "NPI-2",
        "basic": {
            "organization_name": "NASHVILLE TEST CLINIC",
            "status": "A",
            "last_updated": "2026-01-05",
        },
        "addresses": [
            {
                "address_purpose": "MAILING",
                "address_1": "PO BOX 1",
                "city": "NASHVILLE",
                "state": "TN",
                "postal_code": "372010001",
                "telephone_number": "615-555-0000",
            },
            {
                "address_purpose": "LOCATION",
                "address_1": "100 MAIN ST",
                "address_2": "STE 200",
                "city": "NASHVILLE",
                "state": "TN",
                "postal_code": "372030001",
                "telephone_number": "615-555-0100",
            },
        ],
        "taxonomies": [
            {"desc": "Clinic/Center", "primary": False},
            {"desc": "Family Medicine", "primary": True},
        ],
    }

    row = map_npi_record(record, index=1)

    assert row["record_id"] == "NPI-1234567890"
    assert row["npi"] == "1234567890"
    assert row["provider_name"] == "NASHVILLE TEST CLINIC"
    assert row["specialty"] == "Family Medicine"
    assert row["address"] == "100 MAIN ST STE 200"
    assert row["zip"] == "37203"
    assert row["status"] == "active"
    assert row["source_updated_at"] == "2026-01-05"
    assert row["last_verified_date"] == ""


def test_npi_records_to_frame_returns_provider_schema_columns():
    frame = npi_records_to_frame(
        [
            {
                "number": "123",
                "basic": {"first_name": "Ada", "last_name": "Lovelace", "status": "I"},
                "addresses": [],
                "taxonomies": [],
            }
        ]
    )

    assert "provider_name" in frame.columns
    assert frame.loc[0, "provider_name"] == "Ada Lovelace"
    assert frame.loc[0, "status"] == "inactive"


def test_native_npi_record_identity_survives_reordered_results():
    records = [{"number": "1234567890"}, {"number": "0987654321"}]
    first = npi_records_to_frame(records).set_index("npi")["record_id"].to_dict()
    reordered = npi_records_to_frame(list(reversed(records))).set_index("npi")["record_id"].to_dict()

    assert first == reordered == {"1234567890": "NPI-1234567890", "0987654321": "NPI-0987654321"}


def test_unknown_status_and_missing_identity_are_not_invented():
    for basic in [{}, {"status": None}, {"status": "unrecognized"}]:
        row = map_npi_record({"basic": basic}, index=20)
        assert row["status"] == "unknown"
        assert row["record_id"] == ""
        assert row["npi"] == ""


def test_empty_npi_response_retains_export_schema():
    frame = npi_records_to_frame([])
    assert frame.empty
    assert {"record_id", "city", "source_updated_at", "last_verified_date"} <= set(frame.columns)
