"""Factual, read-only intelligence for the JOLIKA portfolio held at UBS."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_diagnostics import diagnose_institution


DecimalItems = tuple[tuple[str, Decimal], ...]
EconomicAllocationItems = tuple[
    tuple[str, tuple[tuple[EconomicAssetClass, Decimal], ...]], ...
]
LegacyAllocationItems = tuple[tuple[str, tuple[tuple[str, Decimal], ...]], ...]


@dataclass(frozen=True)
class PositionExposure:
    """One valued position ranked only within its own currency."""

    asset_label: str
    identifier: str | None
    currency: str
    market_value: Decimal
    weight_within_currency: Decimal | None


@dataclass(frozen=True)
class CurrencyConcentration:
    """Factual concentration metrics for one currency."""

    currency: str
    total_market_value: Decimal
    valued_position_count: int
    top_positions: tuple[PositionExposure, ...]
    top_1_weight: Decimal | None
    top_3_weight: Decimal | None
    top_5_weight: Decimal | None


@dataclass(frozen=True)
class CoverageMetrics:
    """Field-presence counts, without a synthetic score."""

    total_positions: int
    positions_with_market_value: int
    positions_without_market_value: int
    positions_with_identifier: int
    positions_without_identifier: int
    positions_with_economic_class: int
    positions_without_economic_class: int
    positions_with_legacy_asset_class: int
    positions_without_legacy_asset_class: int


@dataclass(frozen=True)
class UBSPortfolioIntelligence:
    """Immutable structural intelligence for UBS/JOLIKA positions."""

    institution: str
    owner: PortfolioOwner
    position_count: int
    currencies: tuple[str, ...]
    totals_by_currency: DecimalItems
    economic_allocation_by_currency: EconomicAllocationItems
    legacy_allocation_by_currency: LegacyAllocationItems
    concentration_by_currency: tuple[CurrencyConcentration, ...]
    coverage: CoverageMetrics
    duplicate_assets: tuple[tuple[str, int], ...]
    warnings: tuple[str, ...]
    source_files: tuple[str, ...]


def _asset_label(position: PortfolioPosition) -> str:
    return position.asset_name or position.identifier or "<unnamed asset>"


def _normalized_identifier(position: PortfolioPosition) -> str:
    return (position.identifier or "").strip().upper()


def _position_sort_key(position: PortfolioPosition) -> tuple:
    """Deterministic ranking tie-breaker after descending market value."""
    return (
        -position.market_value if position.market_value is not None else Decimal("0"),
        _normalized_identifier(position),
        position.asset_name or "",
        position.source_file,
        position.account or "",
        position.asset_class or "",
        position.asset_subclass or "",
        str(position.quantity) if position.quantity is not None else "",
        str(position.unit_price) if position.unit_price is not None else "",
    )


def _freeze_totals(values: dict[str, Decimal]) -> DecimalItems:
    return tuple(sorted(values.items()))


def _freeze_economic_allocation(values) -> EconomicAllocationItems:
    return tuple(
        (
            currency,
            tuple(sorted(allocation.items(), key=lambda item: item[0].value)),
        )
        for currency, allocation in sorted(values.items())
    )


def _legacy_allocation(positions: tuple[PortfolioPosition, ...]) -> LegacyAllocationItems:
    result: dict[str, dict[str, Decimal]] = {}
    for position in positions:
        legacy_class = (position.asset_class or "").strip()
        if (
            position.currency
            and position.market_value is not None
            and legacy_class
        ):
            currency = result.setdefault(position.currency, {})
            currency[legacy_class] = (
                currency.get(legacy_class, Decimal("0")) + position.market_value
            )
    return tuple(
        (currency, tuple(sorted(allocation.items())))
        for currency, allocation in sorted(result.items())
    )


def _coverage(positions: tuple[PortfolioPosition, ...]) -> CoverageMetrics:
    total = len(positions)
    with_value = sum(position.market_value is not None for position in positions)
    with_identifier = sum(
        bool((position.identifier or "").strip()) for position in positions
    )
    with_economic = sum(
        position.economic_asset_class is not None for position in positions
    )
    with_legacy = sum(bool((position.asset_class or "").strip()) for position in positions)
    return CoverageMetrics(
        total_positions=total,
        positions_with_market_value=with_value,
        positions_without_market_value=total - with_value,
        positions_with_identifier=with_identifier,
        positions_without_identifier=total - with_identifier,
        positions_with_economic_class=with_economic,
        positions_without_economic_class=total - with_economic,
        positions_with_legacy_asset_class=with_legacy,
        positions_without_legacy_asset_class=total - with_legacy,
    )


def _top_weight(exposures: tuple[PositionExposure, ...], count: int) -> Decimal | None:
    if not exposures or exposures[0].weight_within_currency is None:
        return None
    return sum(
        (item.weight_within_currency for item in exposures[:count]),
        Decimal("0"),
    )


def _concentration(
    positions: tuple[PortfolioPosition, ...],
    totals_by_currency: dict[str, Decimal],
    *,
    top_n: int,
) -> tuple[CurrencyConcentration, ...]:
    results: list[CurrencyConcentration] = []
    for currency, total in sorted(totals_by_currency.items()):
        valued = tuple(
            sorted(
                (
                    position
                    for position in positions
                    if position.currency == currency and position.market_value is not None
                ),
                key=_position_sort_key,
            )
        )
        all_exposures = tuple(
            PositionExposure(
                asset_label=_asset_label(position),
                identifier=position.identifier,
                currency=currency,
                market_value=position.market_value,
                weight_within_currency=(
                    position.market_value / total if total > 0 else None
                ),
            )
            for position in valued
        )
        results.append(
            CurrencyConcentration(
                currency=currency,
                total_market_value=total,
                valued_position_count=len(valued),
                top_positions=all_exposures[:top_n],
                top_1_weight=_top_weight(all_exposures, 1),
                top_3_weight=_top_weight(all_exposures, 3),
                top_5_weight=_top_weight(all_exposures, 5),
            )
        )
    return tuple(results)


def build_ubs_portfolio_intelligence(
    positions: Iterable[PortfolioPosition],
    *,
    top_n: int = 10,
) -> UBSPortfolioIntelligence:
    """Build deterministic structural intelligence for UBS/JOLIKA positions."""
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")

    canonical_positions = tuple(positions)
    for position in canonical_positions:
        if position.institution != "UBS":
            raise ValueError("all positions must belong to UBS")
        if position.owner is not PortfolioOwner.JOLIKA:
            raise ValueError("all positions must belong to JOLIKA")

    diagnostic = diagnose_institution(canonical_positions)
    totals = dict(diagnostic.market_value_by_currency)

    return UBSPortfolioIntelligence(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        position_count=diagnostic.position_count,
        currencies=diagnostic.currencies,
        totals_by_currency=_freeze_totals(diagnostic.market_value_by_currency),
        economic_allocation_by_currency=_freeze_economic_allocation(
            diagnostic.economic_allocation_by_currency
        ),
        legacy_allocation_by_currency=_legacy_allocation(canonical_positions),
        concentration_by_currency=_concentration(
            canonical_positions,
            totals,
            top_n=top_n,
        ),
        coverage=_coverage(canonical_positions),
        duplicate_assets=tuple(sorted(diagnostic.duplicate_assets.items())),
        warnings=diagnostic.data_quality_warnings,
        source_files=tuple(sorted({position.source_file for position in canonical_positions})),
    )
