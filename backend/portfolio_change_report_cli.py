"""Operational CLI for JOLIKA historical change reports."""

from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
import sys

from backend.portfolio_change_reports import (
    DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY,
    build_portfolio_change_report,
    list_portfolio_change_reports,
    load_portfolio_change_report,
    portfolio_change_report_filename,
    validate_portfolio_change_report_lineage,
    validate_portfolio_change_report_sequence,
    write_portfolio_change_report,
)
from backend.portfolio_snapshots import load_portfolio_snapshot


class OperationalError(ValueError):
    """Expected operator-facing validation error."""


def _parse_timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise OperationalError("invalid generated-at timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperationalError("generated-at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _summary_items(report) -> tuple[tuple[str, int], ...]:
    return tuple((field.name, getattr(report.summary, field.name))
                 for field in fields(report.summary))


def _summary_text(report) -> str:
    return ",".join(f"{name}={value}" for name, value in _summary_items(report))


def _print_summary(report) -> None:
    for name, value in _summary_items(report):
        print(f"{name}: {value}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.portfolio_change_report_cli"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--previous", required=True)
    generate.add_argument("--current", required=True)
    generate.add_argument(
        "--directory",
        default=str(DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY),
    )
    generate.add_argument("--generated-at")
    generate.add_argument("--overwrite", action="store_true")

    listing = subparsers.add_parser("list")
    listing.add_argument(
        "--directory",
        default=str(DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY),
    )

    show = subparsers.add_parser("show")
    show.add_argument("--report", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--report", required=True)
    validate.add_argument("--previous", required=True)
    validate.add_argument("--current", required=True)

    sequence = subparsers.add_parser("validate-sequence")
    sequence.add_argument(
        "--directory",
        default=str(DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY),
    )
    return parser


def _generate(args) -> int:
    previous = load_portfolio_snapshot(args.previous)
    current = load_portfolio_snapshot(args.current)
    if previous.captured_at >= current.captured_at:
        raise OperationalError(
            "previous snapshot must be earlier than current snapshot"
        )

    report = build_portfolio_change_report(
        previous,
        current,
        generated_at=_parse_timestamp(args.generated_at),
    )
    path = Path(args.directory) / portfolio_change_report_filename(report)
    try:
        write_portfolio_change_report(
            report,
            output_path=path,
            overwrite=args.overwrite,
        )
    except FileExistsError as exc:
        raise OperationalError("change report already exists") from exc

    print("Report created")
    print(f"report_id: {report.report_id}")
    print(f"previous_snapshot_id: {report.previous_snapshot_id}")
    print(f"current_snapshot_id: {report.current_snapshot_id}")
    print(f"previous_captured_at: {report.previous_captured_at.isoformat()}")
    print(f"current_captured_at: {report.current_captured_at.isoformat()}")
    print(f"generated_at: {report.generated_at.isoformat()}")
    print(f"previous_positions: {report.previous_position_count}")
    print(f"current_positions: {report.current_position_count}")
    _print_summary(report)
    print(f"path: {path}")
    return 0


def _list(args) -> int:
    reports = list_portfolio_change_reports(args.directory)
    if not reports:
        print("no change reports")
        return 0
    for report in reversed(reports):
        print(
            f"{report.current_captured_at.isoformat()} | "
            f"{report.report_id} | "
            f"previous={report.previous_snapshot_id} | "
            f"current={report.current_snapshot_id} | "
            f"{_summary_text(report)}"
        )
    return 0


def _show(args) -> int:
    report = load_portfolio_change_report(args.report)
    print(f"schema_version: {report.schema_version}")
    print(f"report_id: {report.report_id}")
    print(f"owner: {report.owner.value}")
    print(f"previous_snapshot_id: {report.previous_snapshot_id}")
    print(f"current_snapshot_id: {report.current_snapshot_id}")
    print(f"previous_captured_at: {report.previous_captured_at.isoformat()}")
    print(f"current_captured_at: {report.current_captured_at.isoformat()}")
    print(f"generated_at: {report.generated_at.isoformat()}")
    print(f"previous_position_count: {report.previous_position_count}")
    print(f"current_position_count: {report.current_position_count}")
    _print_summary(report)
    return 0


def _validate(args) -> int:
    report = load_portfolio_change_report(args.report)
    previous = load_portfolio_snapshot(args.previous)
    current = load_portfolio_snapshot(args.current)
    validate_portfolio_change_report_lineage(report, previous, current)
    print("lineage valid")
    return 0


def _validate_sequence(args) -> int:
    reports = list_portfolio_change_reports(args.directory)
    validate_portfolio_change_report_sequence(reports)
    print("sequence valid")
    print(f"reports: {len(reports)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            return _generate(args)
        if args.command == "list":
            return _list(args)
        if args.command == "show":
            return _show(args)
        if args.command == "validate":
            return _validate(args)
        if args.command == "validate-sequence":
            return _validate_sequence(args)
        raise OperationalError(f"unsupported command: {args.command}")
    except (OperationalError, ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
