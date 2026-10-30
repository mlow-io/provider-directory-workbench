from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import load_rule_config
from .export import write_outputs
from .normalize import normalize_provider_frame
from .qa import QAResult, run_quality_checks
from .remediation import run_remediation_checks


def run_pipeline(
    input_csv: Path,
    config_path: Path,
    output_dir: Path,
    sqlite_path: Path,
    as_of: datetime | None = None,
    payer_listings_csv: Path | None = None,
) -> QAResult:
    # Directory identifiers are text, including leading zeroes. Only empty cells
    # are missing; pandas' default NA vocabulary would erase literal source data.
    raw = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    normalized = normalize_provider_frame(raw)
    config = load_rule_config(config_path)
    qa_result = run_quality_checks(normalized, config, as_of=as_of)
    remediation = None
    if payer_listings_csv is not None:
        payer_listings = pd.read_csv(payer_listings_csv, dtype=str, keep_default_na=False)
        remediation = run_remediation_checks(normalized, payer_listings, config.remediation)
    result = QAResult(
        clean_records=qa_result.clean_records,
        exceptions=qa_result.exceptions,
        duplicate_candidates=qa_result.duplicate_candidates,
        summary=qa_result.summary,
        remediation=remediation,
    )
    write_outputs(result, output_dir, sqlite_path, config)
    return result
