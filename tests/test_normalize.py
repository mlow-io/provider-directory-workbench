import pandas as pd

from provider_directory_truth_layer.normalize import (
    normalize_address, normalize_phone, normalize_provider_frame, normalize_text,
)


def test_normalize_phone_strips_punctuation_and_country_code():
    assert normalize_phone("+1 (615) 555-0101") == "6155550101"


def test_normalize_text_uppercases_and_removes_punctuation():
    assert normalize_text(" Sarah Patel, MD ") == "SARAH PATEL MD"


def test_normalize_address_standardizes_common_suffixes():
    assert normalize_address("201 23rd Avenue North Suite 400") == "201 23RD AVE NORTH STE 400"


def test_missing_identifiers_remain_missing_and_zip_zeroes_survive():
    original = pd.DataFrame({"npi": [None, float("nan"), pd.NA, "1234567890"],
                             "zip": ["02108", None, pd.NA, "00501-1234"]})
    normalized = normalize_provider_frame(original)

    assert normalized["npi"].tolist() == ["", "", "", "1234567890"]
    assert normalized["zip"].tolist() == ["02108", "", "", "00501"]
    assert original.loc[0, "npi"] is None
    assert normalized["state"].tolist() == [""] * 4
