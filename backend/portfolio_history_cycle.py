"""Operational orchestration for one complete JOLIKA history cycle.

The cycle deliberately builds and validates every artifact before persistence.
If writing the report unexpectedly fails after a new snapshot was written, only
that newly-created snapshot is removed.  Pre-existing overwritten artifacts are
never deleted or restored because no reliable content backup exists here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path

from backend.asset_resolution import collect_unresolved_jolika_assets
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_change_reports import (
    PortfolioChangeReport,
    build_portfolio_change_report,
    list_portfolio_change_reports,
    portfolio_change_report_filename,
    validate_portfolio_change_report_lineage,
    validate_portfolio_change_report_sequence,
    write_portfolio_change_report,
)
from backend.portfolio_import import import_portfolios
from backend.portfolio_snapshots import (
    PortfolioSnapshot,
    build_portfolio_snapshot,
    list_portfolio_snapshots,
    portfolio_snapshot_filename,
    select_previous_portfolio_snapshot,
    write_portfolio_snapshot,
)


class PortfolioHistoryCycleStatus(str, Enum):
    INITIAL_SNAPSHOT = "INITIAL_SNAPSHOT"
    HISTORICAL_UPDATE = "HISTORICAL_UPDATE"


@dataclass(frozen=True)
class PortfolioHistoryCycleResult:
    status: PortfolioHistoryCycleStatus
    current_snapshot: PortfolioSnapshot
    previous_snapshot: PortfolioSnapshot | None
    change_report: PortfolioChangeReport | None
    snapshot_path: Path
    report_path: Path | None
    position_count: int
    totals_by_currency: dict[str, Decimal]
    warnings: tuple[str, ...]


def _totals_by_currency(
    positions: tuple[PortfolioPosition, ...],
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        totals[position.currency or "UNKNOWN"] += (
            position.market_value or Decimal("0")
        )
    return {currency: totals[currency] for currency in sorted(totals)}


def _dashboard_totals(result: dict) -> dict[str, Decimal] | None:
    raw = result.get("dashboard", {}).get("consolidated", {}).get(
        "totals_by_currency"
    )
    if raw is None:
        return None
    try:
        totals = {currency: Decimal(str(value)) for currency, value in raw.items()}
    except (AttributeError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid dashboard totals_by_currency") from exc
    if any(not value.is_finite() for value in totals.values()):
        raise ValueError("invalid dashboard totals_by_currency")
    return totals


def _warnings(result: dict) -> tuple[str, ...]:
    return tuple(
        f"{diagnostic.get('institution', 'UNKNOWN')}: {warning}"
        for diagnostic in result.get("diagnostics", ())
        for warning in diagnostic.get("warnings", ())
    )


def _validated_import(result: dict) -> tuple[tuple[PortfolioPosition, ...], dict[str, Decimal]]:
    positions = tuple(result.get("positions", ()))
    if not positions:
        raise ValueError("import produced no positions")
    if any(position.owner is not PortfolioOwner.JOLIKA for position in positions):
        raise ValueError("portfolio history cycle accepts JOLIKA positions only")
    institutions = {position.institution.upper() for position in positions}
    if "UBS" not in institutions:
        raise ValueError("portfolio history cycle requires UBS positions")
    if "SANTANDER" not in institutions:
        raise ValueError("portfolio history cycle requires Santander positions")
    unresolved = collect_unresolved_jolika_assets(positions)
    if unresolved:
        keys = ", ".join(item.stable_key for item in unresolved)
        raise ValueError(f"unresolved JOLIKA assets: {len(unresolved)} [{keys}]")
    totals = _totals_by_currency(positions)
    dashboard_totals = _dashboard_totals(result)
    if dashboard_totals is not None and dashboard_totals != totals:
        raise ValueError("portfolio totals do not match dashboard totals_by_currency")
    return positions, totals


def run_portfolio_history_cycle(
    *,
    ubs_path: Path | str,
    santander_path: Path | str,
    snapshot_directory: Path | str,
    report_directory: Path | str,
    captured_at: datetime,
    generated_at: datetime | None = None,
    overwrite: bool = False,
) -> PortfolioHistoryCycleResult:
    """Build, validate and persist one official JOLIKA historical cycle."""
    if not isinstance(captured_at, datetime) or captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    imported = import_portfolios((Path(ubs_path), Path(santander_path)))
    positions, totals = _validated_import(imported)
    snapshots = list_portfolio_snapshots(snapshot_directory)
    previous = select_previous_portfolio_snapshot(snapshots, before=captured_at)
    current = build_portfolio_snapshot(positions, captured_at=captured_at)

    report = None
    existing_reports = ()
    if previous is not None:
        report = build_portfolio_change_report(
            previous,
            current,
            generated_at=current.captured_at if generated_at is None else generated_at,
        )
        validate_portfolio_change_report_lineage(report, previous, current)
        existing_reports = list_portfolio_change_reports(report_directory)

    snapshot_path = Path(snapshot_directory) / portfolio_snapshot_filename(current)
    report_path = (
        None
        if report is None
        else Path(report_directory) / portfolio_change_report_filename(report)
    )
    if not overwrite and snapshot_path.exists():
        raise FileExistsError(f"Output already exists: {snapshot_path}")
    if not overwrite and report_path is not None and report_path.exists():
        raise FileExistsError(f"Output already exists: {report_path}")
    if report is not None:
        validate_portfolio_change_report_sequence((*existing_reports, report))

    snapshot_existed = snapshot_path.exists()
    write_portfolio_snapshot(current, output_path=snapshot_path, overwrite=overwrite)
    try:
        if report is not None and report_path is not None:
            write_portfolio_change_report(
                report, output_path=report_path, overwrite=overwrite
            )
    except BaseException:
        if not snapshot_existed:
            try:
                snapshot_path.unlink()
            except FileNotFoundError:
                pass
        raise

    return PortfolioHistoryCycleResult(
        status=(
            PortfolioHistoryCycleStatus.INITIAL_SNAPSHOT
            if previous is None
            else PortfolioHistoryCycleStatus.HISTORICAL_UPDATE
        ),
        current_snapshot=current,
        previous_snapshot=previous,
        change_report=report,
        snapshot_path=snapshot_path,
        report_path=report_path,
        position_count=len(current.positions),
        totals_by_currency=totals,
        warnings=_warnings(imported),
    )
