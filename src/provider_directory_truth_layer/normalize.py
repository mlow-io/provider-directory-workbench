from __future__ import annotations

import re

import pandas as pd


PHONE_RE = re.compile(r"\D+")
SPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^A-Z0-9 ]+")


def normalize_phone(value: object) -> str:
    if pd.isna(value):
        return ""
    digits = PHONE_RE.sub("", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).upper().strip()
    text = PUNCT_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_address(value: object) -> str:
    text = normalize_text(value)
    replacements = {
        " STREET": " ST",
        " AVENUE": " AVE",
        " ROAD": " RD",
        " DRIVE": " DR",
        " BOULEVARD": " BLVD",
        " SUITE": " STE",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def normalize_provider_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [c.strip().lower() for c in normalized.columns]

    for col in [
        "npi",
        "provider_name",
        "specialty",
        "address",
        "city",
        "state",
        "zip",
        "phone",
        "accepting_new_patients",
        "source",
        "status",
        "last_verified_date",
    ]:
        if col not in normalized.columns:
            normalized[col] = ""

    # Convert missing values before strings: astype(str) alone manufactures "nan".
    # CSV callers must also disable numeric inference; lost ZIP zeroes cannot be
    # recovered safely here without inventing source evidence.
    for col in ["npi", "state", "zip", "status", "accepting_new_patients"]:
        normalized[col] = normalized[col].fillna("").astype(str).str.strip()
    normalized["npi"] = normalized["npi"].str.replace(r"\.0$", "", regex=True)
    normalized["phone_digits"] = normalized["phone"].apply(normalize_phone)
    normalized["normalized_provider_name"] = normalized["provider_name"].apply(normalize_text)
    normalized["normalized_specialty"] = normalized["specialty"].apply(normalize_text)
    normalized["normalized_address"] = normalized["address"].apply(normalize_address)
    normalized["normalized_city"] = normalized["city"].apply(normalize_text)
    normalized["state"] = normalized["state"].str.upper()
    normalized["zip"] = normalized["zip"].str.replace(r"\.0$", "", regex=True).str[:5]
    normalized["status"] = normalized["status"].str.lower()
    normalized["accepting_new_patients"] = (
        normalized["accepting_new_patients"].str.lower()
    )
    normalized["last_verified_date"] = pd.to_datetime(
        normalized["last_verified_date"], errors="coerce"
    )
    return normalized
