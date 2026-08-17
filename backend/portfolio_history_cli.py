"""Thin operational CLI for the complete JOLIKA portfolio history cycle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from backend.portfolio_change_reports import (
    DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY,
)
from backend.portfolio_history_cycle import run_portfolio_history_cycle
from backend.portfolio_snapshots import DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY


SUMMARY_FIELDS = (
    "added",
    "removed",
    "unchanged",
    "quantity_increased",
    "quantity_decreased",
    "account_changed",
    "market_value_changed",
    "unit_price_changed",
    "economic_class_changed",
    "legacy_asset_class_changed",
    "multiple_changes",
    "position_flow_unknown",
)


def _parse_timestamp(value: str, field: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid {field} timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit, side-effect-free command parser."""
    parser = argparse.ArgumentParser(
        prog="python -m backend.portfolio_history_cli"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--ubs", required=True)
    run.add_argument("--santander", required=True)
    run.add_argument(
        "--snapshot-directory",
        default=str(DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY),
    )
    run.add_argument(
        "--report-directory",
        default=str(DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY),
    )
    run.add_argument("--captured-at")
    run.add_argument("--generated-at")
    run.add_argument("--overwrite", action="store_true")
    return parser


def _print_common(result) -> None:
    print(f"positions: {result.position_count}")
    totals = {
        currency: str(value)
        for currency, value in result.totals_by_currency.items()
    }
    print(f"totals_by_currency: {totals}")
    print(f"snapshot_path: {result.snapshot_path}")


def _print_result(result) -> None:
    status = getattr(result.status, "value", result.status)
    print(f"status: {status}")
    if status == "INITIAL_SNAPSHOT":
        print(f"snapshot_id: {result.current_snapshot.snapshot_id}")
        print(f"captured_at: {result.current_snapshot.captured_at.isoformat()}")
        _print_common(result)
        print("report_path: none")
    else:
        report = result.change_report
        previous = result.previous_snapshot
        print(f"previous_snapshot_id: {previous.snapshot_id}")
        print(f"current_snapshot_id: {result.current_snapshot.snapshot_id}")
        print(f"previous_captured_at: {previous.captured_at.isoformat()}")
        print(f"current_captured_at: {result.current_snapshot.captured_at.isoformat()}")
        _print_common(result)
        print(f"report_id: {report.report_id}")
        print(f"report_path: {result.report_path}")
        for field in SUMMARY_FIELDS:
            print(f"{field}: {getattr(report.summary, field)}")
    print(f"warnings_count: {len(result.warnings)}")
    for warning in result.warnings:
        print(f"warning: {warning}")


def _run(args: argparse.Namespace) -> int:
    captured_at = (
        datetime.now(timezone.utc)
        if args.captured_at is None
        else _parse_timestamp(args.captured_at, "captured-at")
    )
    generated_at = (
        None
        if args.generated_at is None
        else _parse_timestamp(args.generated_at, "generated-at")
    )
    result = run_portfolio_history_cycle(
        ubs_path=args.ubs,
        santander_path=args.santander,
        snapshot_directory=Path(args.snapshot_directory),
        report_directory=Path(args.report_directory),
        captured_at=captured_at,
        generated_at=generated_at,
        overwrite=args.overwrite,
    )
    _print_result(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return _run(args)
        raise ValueError(f"unsupported command: {args.command}")
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
