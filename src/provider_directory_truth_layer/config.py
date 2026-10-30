from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_REMEDIATION_FIELDS = [
    "npi",
    "provider_name",
    "specialty",
    "address",
    "city",
    "state",
    "zip",
    "phone",
    "accepting_new_patients",
    "status",
]

DEFAULT_FIELD_SOURCE_PRECEDENCE = {
    "npi": ["NPPES-like export", "health-system roster", "clinic directory", "payer directory"],
    "provider_name": [
        "NPPES-like export",
        "health-system roster",
        "clinic directory",
        "payer directory",
    ],
    "specialty": ["health-system roster", "clinic directory", "NPPES-like export", "payer directory"],
    "address": ["clinic directory", "health-system roster", "NPPES-like export", "payer directory"],
    "city": ["clinic directory", "health-system roster", "NPPES-like export", "payer directory"],
    "state": ["clinic directory", "health-system roster", "NPPES-like export", "payer directory"],
    "zip": ["clinic directory", "health-system roster", "NPPES-like export", "payer directory"],
    "phone": ["clinic directory", "health-system roster", "NPPES-like export", "payer directory"],
    "accepting_new_patients": [
        "clinic directory",
        "health-system roster",
        "payer directory",
    ],
    "status": ["health-system roster", "clinic directory", "payer directory", "NPPES-like export"],
}

DEFAULT_RISK_BY_FIELD = {
    "npi": "high",
    "provider_name": "medium",
    "specialty": "medium",
    "address": "high",
    "city": "high",
    "state": "high",
    "zip": "high",
    "phone": "high",
    "accepting_new_patients": "medium",
    "status": "high",
}


@dataclass(frozen=True)
class RemediationConfig:
    comparison_fields: list[str]
    field_source_precedence: dict[str, list[str]]
    risk_by_field: dict[str, str]


@dataclass(frozen=True)
class RuleConfig:
    required_fields: list[str]
    phone_min_digits: int
    active_status_values: set[str]
    stale_days_threshold: int
    duplicate_match_fields: list[str]
    remediation: RemediationConfig


def load_rule_config(path: Path) -> RuleConfig:
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    remediation_data: dict[str, Any] = data.get("remediation", {}) or {}
    comparison_fields = list(remediation_data.get("comparison_fields", DEFAULT_REMEDIATION_FIELDS))
    raw_precedence = remediation_data.get("field_source_precedence", {}) or {}
    field_source_precedence = {
        field: list(raw_precedence.get(field, DEFAULT_FIELD_SOURCE_PRECEDENCE.get(field, [])))
        for field in comparison_fields
    }
    raw_risks = remediation_data.get("risk_by_field", {}) or {}
    risk_by_field = {
        field: str(raw_risks.get(field, DEFAULT_RISK_BY_FIELD.get(field, "")))
        for field in comparison_fields
    }
    remediation = RemediationConfig(
        comparison_fields=comparison_fields,
        field_source_precedence=field_source_precedence,
        risk_by_field=risk_by_field,
    )
    _validate_remediation_config(remediation)
    return RuleConfig(
        required_fields=list(data.get("required_fields", [])),
        phone_min_digits=int(data.get("phone_min_digits", 10)),
        active_status_values=set(data.get("active_status_values", ["active"])),
        stale_days_threshold=int(data.get("stale_days_threshold", 365)),
        duplicate_match_fields=list(
            data.get(
                "duplicate_match_fields",
                ["normalized_provider_name", "normalized_address", "normalized_city", "state"],
            )
        ),
        remediation=remediation,
    )


def _validate_remediation_config(config: RemediationConfig) -> None:
    valid_risks = {"high", "medium", "low"}
    for field in config.comparison_fields:
        sources = config.field_source_precedence.get(field, [])
        if not sources:
            raise ValueError(f"Field source precedence is required for remediation field: {field}")
        if len({source.casefold() for source in sources}) != len(sources):
            raise ValueError(f"Field source precedence cannot repeat a source for: {field}")
        risk = config.risk_by_field.get(field)
        if risk not in valid_risks:
            raise ValueError(f"Remediation risk must be high, medium, or low for: {field}")
