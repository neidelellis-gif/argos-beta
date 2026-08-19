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
from backend.portfolio_history_preflight import run_portfolio_history_preflight
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


def _add_common_input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ubs", required=True)
    parser.add_argument("--santander", required=True)
    parser.add_argument(
        "--snapshot-directory",
        default=str(DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY),
    )
    parser.add_argument("--captured-at")


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit, side-effect-free command parser."""
    parser = argparse.ArgumentParser(
        prog="python -m backend.portfolio_history_cli"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    _add_common_input_arguments(run)
    run.add_argument(
        "--report-directory",
        default=str(DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY),
    )
    run.add_argument("--generated-at")
    run.add_argument("--overwrite", action="store_true")

    preflight = subparsers.add_parser("preflight")
    _add_common_input_arguments(preflight)
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


def _print_preflight(result) -> None:
    totals = {currency: str(value) for currency, value in result.totals_by_currency}
    print(f"preflight_approved: {str(result.approved).lower()}")
    print(f"preflight_total_positions: {result.total_position_count}")
    print(f"preflight_ubs_positions: {result.ubs.position_count}")
    print(f"preflight_santander_positions: {result.santander.position_count}")
    print(f"preflight_unresolved: {result.unresolved_count}")
    print(f"preflight_totals_by_currency: {totals}")
    print(f"preflight_baseline_snapshot_id: {result.baseline_snapshot_id or 'none'}")
    baseline_count = (
        "none"
        if result.baseline_position_count is None
        else result.baseline_position_count
    )
    print(f"preflight_baseline_position_count: {baseline_count}")
    position_count_change = (
        "none"
        if result.position_count_change is None
        else result.position_count_change
    )
    print(f"preflight_position_count_change: {position_count_change}")
    print(f"preflight_warnings_count: {len(result.warnings)}")
    print(f"preflight_blockers_count: {len(result.blockers)}")
    for warning in result.warnings:
        print(f"preflight_warning: {warning}")
    for blocker in result.blockers:
        print(f"preflight_blocker: {blocker}")


def _captured_at(args: argparse.Namespace) -> datetime:
    return (
        datetime.now(timezone.utc)
        if args.captured_at is None
        else _parse_timestamp(args.captured_at, "captured-at")
    )


def _run_preflight(args: argparse.Namespace) -> int:
    captured_at = _captured_at(args)
    result = run_portfolio_history_preflight(
        ubs_path=args.ubs,
        santander_path=args.santander,
        snapshot_directory=Path(args.snapshot_directory),
        before=captured_at,
    )
    _print_preflight(result)
    return 0 if result.approved else 2


def _run(args: argparse.Namespace) -> int:
    captured_at = _captured_at(args)
    generated_at = (
        None
        if args.generated_at is None
        else _parse_timestamp(args.generated_at, "generated-at")
    )
    preflight = run_portfolio_history_preflight(
        ubs_path=args.ubs,
        santander_path=args.santander,
        snapshot_directory=Path(args.snapshot_directory),
        before=captured_at,
    )
    _print_preflight(preflight)
    if not preflight.approved:
        return 2
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
        if args.command == "preflight":
            return _run_preflight(args)
        raise ValueError(f"unsupported command: {args.command}")
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
