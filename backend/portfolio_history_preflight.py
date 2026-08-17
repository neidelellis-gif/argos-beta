"""Read-only operational checks before an official JOLIKA history cycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from backend.asset_resolution import collect_unresolved_jolika_assets
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_import import import_portfolios
from backend.portfolio_snapshots import (
    list_portfolio_snapshots,
    select_previous_portfolio_snapshot,
)


@dataclass(frozen=True)
class PortfolioInputInstitutionSummary:
    """Facts reported for one expected input institution."""

    institution: str
    file_name: str
    position_count: int
    totals_by_currency: tuple[tuple[str, Decimal], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioHistoryPreflightResult:
    """Immutable evidence used to decide whether a history cycle may start."""

    approved: bool
    ubs: PortfolioInputInstitutionSummary
    santander: PortfolioInputInstitutionSummary
    total_position_count: int
    totals_by_currency: tuple[tuple[str, Decimal], ...]
    unresolved_count: int
    unresolved_keys: tuple[str, ...]
    baseline_snapshot_id: str | None
    baseline_captured_at: datetime | None
    baseline_position_count: int | None
    position_count_change: int | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]


def _totals(positions: tuple[PortfolioPosition, ...]) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for position in positions:
        currency = position.currency or ""
        value = Decimal("0") if position.market_value is None else position.market_value
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("position market_value must be a finite Decimal or None")
        totals[currency] = totals.get(currency, Decimal("0")) + value
    return tuple(sorted(totals.items()))


def _dashboard_totals(payload: object) -> tuple[tuple[str, Decimal], ...] | None:
    if not isinstance(payload, Mapping):
        return None
    consolidated = payload.get("consolidated")
    if not isinstance(consolidated, Mapping):
        return None
    raw_totals = consolidated.get("totals_by_currency")
    if not isinstance(raw_totals, Mapping):
        return None
    converted: list[tuple[str, Decimal]] = []
    try:
        for currency, value in raw_totals.items():
            decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
            if not decimal_value.is_finite():
                return ()
            converted.append((str(currency), decimal_value))
    except (InvalidOperation, ValueError, TypeError):
        return ()
    return tuple(sorted(converted))


def _summary(
    institution: str,
    path: Path,
    positions: tuple[PortfolioPosition, ...],
    diagnostics: tuple[Mapping, ...],
) -> PortfolioInputInstitutionSummary:
    institution_positions = tuple(
        position for position in positions if position.institution == institution
    )
    warnings = tuple(
        str(warning)
        for diagnostic in diagnostics
        if diagnostic.get("institution") == institution
        for warning in diagnostic.get("warnings", ())
    )
    try:
        totals_by_currency = _totals(institution_positions)
    except ValueError:
        totals_by_currency = ()
    return PortfolioInputInstitutionSummary(
        institution=institution,
        file_name=path.name,
        position_count=len(institution_positions),
        totals_by_currency=totals_by_currency,
        warnings=warnings,
    )


def run_portfolio_history_preflight(
    *,
    ubs_path,
    santander_path,
    snapshot_directory=None,
    before=None,
) -> PortfolioHistoryPreflightResult:
    """Import two sources and return factual, non-persistent preflight evidence."""
    ubs_source = Path(ubs_path)
    santander_source = Path(santander_path)
    imported = import_portfolios((ubs_source, santander_source))
    positions = tuple(imported.get("positions", ()))
    files = tuple(imported.get("files", ()))
    diagnostics = tuple(imported.get("diagnostics", ()))

    blockers: list[str] = []
    warnings = [
        str(warning)
        for diagnostic in diagnostics
        for warning in diagnostic.get("warnings", ())
    ]

    expected = ((ubs_source, "UBS"), (santander_source, "Santander"))
    for index, (source, institution) in enumerate(expected):
        actual = files[index].get("institution") if index < len(files) else None
        if actual != institution:
            warnings.append(
                f"source file institution mismatch: {source.name} expected {institution}, got {actual or 'missing'}"
            )
            blockers.append("source file institution mismatch")

    total_position_count = len(positions)
    if not positions:
        blockers.append("no positions")
    non_jolika_count = sum(
        position.owner is not PortfolioOwner.JOLIKA for position in positions
    )
    if non_jolika_count:
        blockers.append(f"non-JOLIKA positions: {non_jolika_count}")

    ubs = _summary("UBS", ubs_source, positions, diagnostics)
    santander = _summary("Santander", santander_source, positions, diagnostics)
    if not ubs.position_count:
        blockers.append("missing UBS positions")
    if not santander.position_count:
        blockers.append("missing Santander positions")

    jolika_positions = tuple(
        position for position in positions if position.owner is PortfolioOwner.JOLIKA
    )
    unresolved = collect_unresolved_jolika_assets(jolika_positions)
    if unresolved:
        blockers.append(f"unresolved JOLIKA assets: {len(unresolved)}")

    try:
        totals_by_currency = _totals(positions)
    except ValueError:
        totals_by_currency = ()
        blockers.append("non-finite totals_by_currency")

    dashboard_totals = _dashboard_totals(imported.get("dashboard"))
    if dashboard_totals is not None and dashboard_totals != totals_by_currency:
        blockers.append("dashboard totals mismatch")

    baseline = None
    if snapshot_directory is not None:
        cutoff = before or datetime.now(timezone.utc)
        baseline = select_previous_portfolio_snapshot(
            list_portfolio_snapshots(snapshot_directory), before=cutoff
        )
    baseline_count = None if baseline is None else len(baseline.positions)
    position_count_change = (
        None if baseline_count is None else total_position_count - baseline_count
    )
    if baseline_count is not None and total_position_count < baseline_count:
        warnings.append(
            f"current position count below baseline: {total_position_count} < {baseline_count}"
        )

    unique_blockers = tuple(dict.fromkeys(blockers))
    return PortfolioHistoryPreflightResult(
        approved=not unique_blockers,
        ubs=ubs,
        santander=santander,
        total_position_count=total_position_count,
        totals_by_currency=totals_by_currency,
        unresolved_count=len(unresolved),
        unresolved_keys=tuple(asset.stable_key for asset in unresolved),
        baseline_snapshot_id=None if baseline is None else baseline.snapshot_id,
        baseline_captured_at=None if baseline is None else baseline.captured_at,
        baseline_position_count=baseline_count,
        position_count_change=position_count_change,
        warnings=tuple(warnings),
        blockers=unique_blockers,
    )
