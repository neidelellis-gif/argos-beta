"""Operational CLI for explicit JOLIKA portfolio snapshot workflows."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import sys

from backend.asset_resolution import collect_unresolved_jolika_assets
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_changes import serialize_portfolio_change_set
from backend.portfolio_import import import_portfolios
from backend.portfolio_snapshots import (
    DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY,
    PortfolioSnapshot,
    build_portfolio_snapshot,
    compare_portfolio_snapshot_objects,
    compare_snapshot_to_positions,
    list_portfolio_snapshots,
    load_portfolio_snapshot,
    portfolio_snapshot_filename,
    select_previous_portfolio_snapshot,
    write_portfolio_snapshot,
)


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
        raise OperationalError("invalid captured-at timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperationalError("captured-at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _totals_by_currency(positions: tuple[PortfolioPosition, ...]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        currency = position.currency or "UNKNOWN"
        totals[currency] += position.market_value or Decimal("0")
    return {currency: totals[currency] for currency in sorted(totals)}


def _string_totals(totals: dict[str, Decimal]) -> dict[str, str]:
    return {currency: str(value) for currency, value in totals.items()}


def _warnings(result: dict) -> tuple[str, ...]:
    messages: list[str] = []
    for diagnostic in result.get("diagnostics", ()):  # defensive for tests/older callers
        for warning in diagnostic.get("warnings", ()):
            messages.append(f"{diagnostic.get('institution', 'UNKNOWN')}: {warning}")
    return tuple(messages)


def _load_current_jolika_portfolio(ubs: Path | str, santander: Path | str):
    result = import_portfolios((Path(ubs), Path(santander)))
    positions = tuple(result["positions"])
    if not positions:
        raise OperationalError("import produced no positions")
    if any(position.owner is not PortfolioOwner.JOLIKA for position in positions):
        raise OperationalError("operational snapshot workflow accepts JOLIKA positions only")

    institutions = {position.institution.upper() for position in positions}
    if "UBS" not in institutions or "SANTANDER" not in institutions:
        raise OperationalError("capture requires both UBS and Santander positions")

    unresolved = collect_unresolved_jolika_assets(positions)
    if unresolved:
        keys = ", ".join(item.stable_key for item in unresolved)
        raise OperationalError(
            f"unresolved JOLIKA assets: {len(unresolved)} [{keys}]"
        )

    actual = _totals_by_currency(positions)
    dashboard_totals = (
        result.get("dashboard", {})
        .get("consolidated", {})
        .get("totals_by_currency")
    )
    if dashboard_totals is not None:
        expected = {currency: Decimal(str(value)) for currency, value in dashboard_totals.items()}
        if expected != actual:
            raise OperationalError("portfolio totals do not match dashboard totals_by_currency")

    return result, positions, actual


def _write_atomic_text(path: Path, text: str, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _print_warnings(result: dict) -> None:
    for warning in _warnings(result):
        print(f"warning: {warning}")


def _change_summary(changes) -> dict[str, int]:
    return {
        "added": changes.added_count,
        "removed": changes.removed_count,
        "unchanged": changes.unchanged_count,
        "quantity_increased": changes.quantity_increased_count,
        "quantity_decreased": changes.quantity_decreased_count,
        "account_changed": changes.account_changed_count,
        "economic_class_changed": changes.economic_class_changed_count,
    }


def _print_change_summary(changes) -> None:
    for key, value in _change_summary(changes).items():
        print(f"{key}: {value}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.portfolio_snapshot_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--ubs", required=True)
    capture.add_argument("--santander", required=True)
    capture.add_argument("--directory", default=str(DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY))
    capture.add_argument("--captured-at")
    capture.add_argument("--overwrite", action="store_true")

    listing = subparsers.add_parser("list")
    listing.add_argument("--directory", default=str(DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY))

    show = subparsers.add_parser("show")
    show.add_argument("--snapshot", required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--previous", required=True)
    compare.add_argument("--current", required=True)
    compare.add_argument("--output")
    compare.add_argument("--overwrite", action="store_true")

    current = subparsers.add_parser("compare-current")
    current.add_argument("--ubs", required=True)
    current.add_argument("--santander", required=True)
    current.add_argument("--directory", default=str(DEFAULT_PORTFOLIO_SNAPSHOT_DIRECTORY))
    current.add_argument("--captured-at")
    return parser


def _capture(args) -> int:
    result, positions, totals = _load_current_jolika_portfolio(args.ubs, args.santander)
    _print_warnings(result)
    snapshot = build_portfolio_snapshot(
        positions,
        captured_at=_parse_timestamp(args.captured_at),
    )
    directory = Path(args.directory)
    path = directory / portfolio_snapshot_filename(snapshot)
    try:
        write_portfolio_snapshot(snapshot, output_path=path, overwrite=args.overwrite)
    except FileExistsError as exc:
        raise OperationalError("snapshot already exists") from exc

    print("Snapshot created")
    print(f"snapshot_id: {snapshot.snapshot_id}")
    print(f"captured_at: {snapshot.captured_at.isoformat()}")
    print(f"positions: {len(snapshot.positions)}")
    print(f"institutions: {', '.join(snapshot.institutions)}")
    print(f"source_files: {', '.join(snapshot.source_files)}")
    print(f"totals_by_currency: {_string_totals(totals)}")
    print(f"path: {path}")
    return 0


def _list(args) -> int:
    snapshots = list_portfolio_snapshots(args.directory)
    if not snapshots:
        print("no snapshots")
        return 0
    for snapshot in reversed(snapshots):
        print(
            f"{snapshot.captured_at.isoformat()} | {snapshot.snapshot_id} | "
            f"positions={len(snapshot.positions)} | "
            f"institutions={','.join(snapshot.institutions)} | "
            f"source_files={','.join(snapshot.source_files)}"
        )
    return 0


def _show(args) -> int:
    snapshot = load_portfolio_snapshot(args.snapshot)
    totals = _totals_by_currency(snapshot.positions)
    print(f"schema_version: {snapshot.schema_version}")
    print(f"snapshot_id: {snapshot.snapshot_id}")
    print(f"owner: {snapshot.owner.value}")
    print(f"captured_at: {snapshot.captured_at.isoformat()}")
    print(f"position_count: {len(snapshot.positions)}")
    print(f"institutions: {', '.join(snapshot.institutions)}")
    print(f"source_files: {', '.join(snapshot.source_files)}")
    print(f"reference_dates: {', '.join(snapshot.reference_dates)}")
    print(f"totals_by_currency: {_string_totals(totals)}")
    return 0


def _compare(args) -> int:
    previous = load_portfolio_snapshot(args.previous)
    current = load_portfolio_snapshot(args.current)
    if previous.captured_at >= current.captured_at:
        raise OperationalError("previous snapshot must be earlier than current snapshot")
    changes = compare_portfolio_snapshot_objects(previous, current)
    print(f"previous_snapshot_id: {previous.snapshot_id}")
    print(f"previous_captured_at: {previous.captured_at.isoformat()}")
    print(f"current_snapshot_id: {current.snapshot_id}")
    print(f"current_captured_at: {current.captured_at.isoformat()}")
    print(f"previous_positions: {changes.total_previous_positions}")
    print(f"current_positions: {changes.total_current_positions}")
    _print_change_summary(changes)
    if args.output:
        try:
            _write_atomic_text(
                Path(args.output),
                serialize_portfolio_change_set(changes),
                overwrite=args.overwrite,
            )
        except FileExistsError as exc:
            raise OperationalError(str(exc)) from exc
        print(f"change_set_path: {args.output}")
    return 0


def _compare_current(args) -> int:
    result, positions, totals = _load_current_jolika_portfolio(args.ubs, args.santander)
    _print_warnings(result)
    current_at = _parse_timestamp(args.captured_at)
    snapshots = list_portfolio_snapshots(args.directory)
    baseline = select_previous_portfolio_snapshot(snapshots, before=current_at)
    if baseline is None:
        print("no historical baseline")
        return 0
    changes = compare_snapshot_to_positions(baseline, positions)
    assert changes is not None
    print(f"baseline_snapshot_id: {baseline.snapshot_id}")
    print(f"baseline_captured_at: {baseline.captured_at.isoformat()}")
    print(f"current_captured_at: {current_at.astimezone(timezone.utc).isoformat()}")
    print(f"current_positions: {len(positions)}")
    print(f"totals_by_currency: {_string_totals(totals)}")
    _print_change_summary(changes)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            return _capture(args)
        if args.command == "list":
            return _list(args)
        if args.command == "show":
            return _show(args)
        if args.command == "compare":
            return _compare(args)
        if args.command == "compare-current":
            return _compare_current(args)
        raise OperationalError(f"unsupported command: {args.command}")
    except (OperationalError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
