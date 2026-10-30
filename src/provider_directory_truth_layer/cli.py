from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from .npi_api import fetch_npi_records, write_npi_sample_csv
from .pipeline import run_pipeline
from .storage import database_path, output_path, storage_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run provider directory normalization, QA, duplicate detection, and exception exports."
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run QA against a local provider-directory CSV.")
    add_run_arguments(run_parser)

    fetch_parser = subparsers.add_parser(
        "fetch-npi",
        help="Fetch a small public NPI Registry API sample, write it to CSV, and run QA.",
    )
    fetch_parser.add_argument("--city", type=str, default="Nashville")
    fetch_parser.add_argument("--state", type=str, default="TN")
    fetch_parser.add_argument("--limit", type=int, default=25)
    fetch_parser.add_argument(
        "--raw-output",
        type=Path,
        default=storage_root() / "npi_registry_sample_nashville.csv",
    )
    add_run_arguments(fetch_parser, include_input=False)

    # Backward-compatible legacy arguments: `provider-truth-layer --as-of ...`
    add_run_arguments(parser)
    return parser


def add_run_arguments(
    parser: argparse.ArgumentParser,
    include_input: bool = True,
) -> None:
    if include_input:
        parser.add_argument("--input", type=Path, default=Path("data/raw/sample_provider_directory.csv"))
    parser.add_argument("--config", type=Path, default=Path("config/qa_rules.yml"))
    parser.add_argument("--output-dir", type=Path, default=output_path())
    parser.add_argument(
        "--payer-listings",
        type=Path,
        help="Optional payer-directory listing CSV; enables Phase 1 verification comparisons.",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=database_path(),
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Optional YYYY-MM-DD date for stale-record calculations.",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    if args.command == "fetch-npi":
        request_limit = min(max(args.limit * 4, args.limit), 200)
        records = fetch_npi_records(
            args.city,
            args.state,
            limit=args.limit,
            request_limit=request_limit,
        )
        input_csv = write_npi_sample_csv(
            records,
            args.raw_output,
            city_filter=args.city,
            state_filter=args.state,
            limit=args.limit,
        )
        print(f"fetched_records: {len(records)}")
        print(f"raw_output: {input_csv}")
        print(f"sample_records: {len(pd.read_csv(input_csv))}")
    else:
        input_csv = args.input

    result = run_pipeline(
        input_csv,
        args.config,
        args.output_dir,
        args.sqlite,
        as_of=as_of,
        payer_listings_csv=args.payer_listings,
    )
    summary = {row["metric"]: row["value"] for _, row in result.summary.iterrows()}
    print("Provider Directory Truth Layer run complete")
    print(f"records: {summary.get('total_records', 0)}")
    print(f"records_with_issues: {summary.get('records_with_issues', 0)}")
    print(f"total_issues: {summary.get('total_issues', 0)}")
    if result.remediation is not None:
        print(f"payer_listings: {len(result.remediation.payer_listings)}")
        print(f"field_discrepancies: {len(result.remediation.discrepancies)}")
    print(f"outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
