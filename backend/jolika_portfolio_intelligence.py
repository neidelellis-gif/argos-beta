"""Factual, read-only portfolio intelligence for the consolidated JOLIKA portfolio."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_consolidation import (
    ConsolidatedPortfolio,
    ConsolidatedPosition,
    PortfolioConsolidationEngine,
)


DecimalItems = tuple[tuple[str, Decimal], ...]
EconomicAllocationItems = tuple[
    tuple[str, tuple[tuple[EconomicAssetClass, Decimal], ...]],
    ...,
]


@dataclass(frozen=True)
class JolikaPositionExposure:
    """One consolidated JOLIKA asset ranked inside its own currency."""

    asset_label: str
    identifier: str | None
    currency: str
    market_value: Decimal
    weight_within_currency: Decimal | None
    institution_count: int
    institutions: tuple[str, ...]


@dataclass(frozen=True)
class JolikaCurrencyConcentration:
    """Factual concentration metrics for one portfolio currency."""

    currency: str
    total_market_value: Decimal
    asset_count: int
    top_positions: tuple[JolikaPositionExposure, ...]
    top_1_weight: Decimal | None
    top_3_weight: Decimal | None
    top_5_weight: Decimal | None


@dataclass(frozen=True)
class JolikaCoverageMetrics:
    """Coverage facts for the consolidated JOLIKA portfolio."""

    original_position_count: int
    consolidated_asset_count: int
    assets_with_economic_class: int
    assets_without_economic_class: int
    assets_with_identifier: int
    assets_without_identifier: int


@dataclass(frozen=True)
class JolikaDuplicateExposure:
    """One economic asset represented by more than one source position."""

    asset_key: str
    institutions: tuple[str, ...]
    within_same_institution: bool
    across_institutions: bool
    source_position_count: int


@dataclass(frozen=True)
class JolikaPriorityAssessment:
    """Priority for analysis and monitoring, never a transaction recommendation."""

    level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class JolikaStructuralMateriality:
    """Structural relevance of the strongest portfolio exposure."""

    level: str
    max_position_weight: Decimal
    driver: str | None


@dataclass(frozen=True)
class JolikaStructuralDiversification:
    """Structural diversification measured from asset and class concentration."""

    level: str
    asset_hhi: Decimal
    class_hhi: Decimal
    driver: str | None


@dataclass(frozen=True)
class JolikaPortfolioIntelligence:
    """Immutable structural intelligence for the consolidated JOLIKA portfolio."""

    owner: PortfolioOwner
    original_position_count: int
    consolidated_asset_count: int
    institutions: tuple[str, ...]
    currencies: tuple[str, ...]
    totals_by_currency: DecimalItems
    economic_allocation_by_currency: EconomicAllocationItems
    concentration_by_currency: tuple[JolikaCurrencyConcentration, ...]
    coverage: JolikaCoverageMetrics
    duplicate_exposures: tuple[JolikaDuplicateExposure, ...]
    consolidation_alerts: tuple[str, ...]
    priority: JolikaPriorityAssessment
    materiality: JolikaStructuralMateriality
    diversification: JolikaStructuralDiversification
    source_files: tuple[str, ...]


def _asset_label(position: ConsolidatedPosition) -> str:
    return position.asset_name or position.identifier or "<unnamed asset>"


def _position_sort_key(position: ConsolidatedPosition) -> tuple:
    return (
        -position.market_value,
        (position.identifier or "").strip().upper(),
        position.asset_name or "",
        position.currency or "",
    )


def _top_weight(
    exposures: tuple[JolikaPositionExposure, ...],
    count: int,
) -> Decimal | None:
    weights = tuple(
        exposure.weight_within_currency
        for exposure in exposures[:count]
        if exposure.weight_within_currency is not None
    )
    if not weights:
        return None
    return sum(weights, Decimal("0"))


def _totals_by_currency(
    portfolio: ConsolidatedPortfolio,
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for position in portfolio.positions:
        if not position.currency:
            continue
        totals[position.currency] = (
            totals.get(position.currency, Decimal("0"))
            + position.market_value
        )
    return totals


def _economic_allocation_by_currency(
    portfolio: ConsolidatedPortfolio,
) -> dict[str, dict[EconomicAssetClass, Decimal]]:
    result: dict[str, dict[EconomicAssetClass, Decimal]] = {}

    for position in portfolio.positions:
        if not position.currency or position.economic_asset_class is None:
            continue

        allocation = result.setdefault(position.currency, {})
        allocation[position.economic_asset_class] = (
            allocation.get(position.economic_asset_class, Decimal("0"))
            + position.market_value
        )

    return result


def _freeze_totals(values: dict[str, Decimal]) -> DecimalItems:
    return tuple(sorted(values.items()))


def _freeze_economic_allocation(
    values: dict[str, dict[EconomicAssetClass, Decimal]],
) -> EconomicAllocationItems:
    return tuple(
        (
            currency,
            tuple(
                sorted(
                    allocation.items(),
                    key=lambda item: item[0].value,
                )
            ),
        )
        for currency, allocation in sorted(values.items())
    )


def _concentration(
    portfolio: ConsolidatedPortfolio,
    totals_by_currency: dict[str, Decimal],
    *,
    top_n: int,
) -> tuple[JolikaCurrencyConcentration, ...]:
    results: list[JolikaCurrencyConcentration] = []

    for currency, total in sorted(totals_by_currency.items()):
        positions = tuple(
            sorted(
                (
                    position
                    for position in portfolio.positions
                    if position.currency == currency
                ),
                key=_position_sort_key,
            )
        )

        exposures = tuple(
            JolikaPositionExposure(
                asset_label=_asset_label(position),
                identifier=position.identifier,
                currency=currency,
                market_value=position.market_value,
                weight_within_currency=(
                    position.market_value / total
                    if total > 0
                    else None
                ),
                institution_count=len(
                    {origin.institution for origin in position.origins}
                ),
                institutions=tuple(
                    sorted(
                        {origin.institution for origin in position.origins}
                    )
                ),
            )
            for position in positions
        )

        results.append(
            JolikaCurrencyConcentration(
                currency=currency,
                total_market_value=total,
                asset_count=len(positions),
                top_positions=exposures[:top_n],
                top_1_weight=_top_weight(exposures, 1),
                top_3_weight=_top_weight(exposures, 3),
                top_5_weight=_top_weight(exposures, 5),
            )
        )

    return tuple(results)


def _coverage(
    portfolio: ConsolidatedPortfolio,
) -> JolikaCoverageMetrics:
    positions = portfolio.positions

    with_economic_class = sum(
        position.economic_asset_class is not None
        for position in positions
    )
    with_identifier = sum(
        bool((position.identifier or "").strip())
        for position in positions
    )

    total = len(positions)

    return JolikaCoverageMetrics(
        original_position_count=portfolio.report.statistics.original_positions,
        consolidated_asset_count=total,
        assets_with_economic_class=with_economic_class,
        assets_without_economic_class=total - with_economic_class,
        assets_with_identifier=with_identifier,
        assets_without_identifier=total - with_identifier,
    )


def _duplicates(
    portfolio: ConsolidatedPortfolio,
) -> tuple[JolikaDuplicateExposure, ...]:
    return tuple(
        JolikaDuplicateExposure(
            asset_key=duplicate.asset_key,
            institutions=duplicate.institutions,
            within_same_institution=duplicate.within_same_institution,
            across_institutions=duplicate.across_institutions,
            source_position_count=len(duplicate.origins),
        )
        for duplicate in portfolio.report.duplicates
    )


def _priority(
    concentration: tuple[JolikaCurrencyConcentration, ...],
    coverage: JolikaCoverageMetrics,
    duplicates: tuple[JolikaDuplicateExposure, ...],
) -> JolikaPriorityAssessment:
    """Classify analysis/monitoring priority from objective structural facts."""
    high_reasons: list[str] = []
    medium_reasons: list[str] = []

    top_1_weights = tuple(
        item.top_1_weight
        for item in concentration
        if item.top_1_weight is not None
    )
    max_top_1 = max(top_1_weights, default=Decimal("0"))

    if max_top_1 >= Decimal("0.35"):
        high_reasons.append("concentration")
    elif max_top_1 > Decimal("0.20"):
        medium_reasons.append("concentration")

    if coverage.consolidated_asset_count:
        coverage_ratio = (
            Decimal(coverage.assets_with_economic_class)
            / Decimal(coverage.consolidated_asset_count)
        )
        if coverage_ratio < Decimal("0.80"):
            high_reasons.append("coverage")
        elif coverage_ratio < Decimal("0.95"):
            medium_reasons.append("coverage")

    if any(item.across_institutions for item in duplicates):
        medium_reasons.append("cross_institution_duplicate")

    if high_reasons:
        return JolikaPriorityAssessment(
            level="Alta",
            reasons=tuple(dict.fromkeys(high_reasons + medium_reasons)),
        )

    if medium_reasons:
        return JolikaPriorityAssessment(
            level="Média",
            reasons=tuple(dict.fromkeys(medium_reasons)),
        )

    return JolikaPriorityAssessment(
        level="Baixa",
        reasons=(),
    )


def _materiality(
    concentration: tuple[JolikaCurrencyConcentration, ...],
) -> JolikaStructuralMateriality:
    """Classify structural materiality from the strongest position weight."""
    weights = tuple(
        item.top_1_weight
        for item in concentration
        if item.top_1_weight is not None
    )
    max_weight = max(weights, default=Decimal("0"))

    if max_weight >= Decimal("0.35"):
        return JolikaStructuralMateriality(
            level="Alta",
            max_position_weight=max_weight,
            driver="concentration",
        )

    if max_weight > Decimal("0.20"):
        return JolikaStructuralMateriality(
            level="Média",
            max_position_weight=max_weight,
            driver="concentration",
        )

    return JolikaStructuralMateriality(
        level="Baixa",
        max_position_weight=max_weight,
        driver=None,
    )


def _diversification(
    portfolio: ConsolidatedPortfolio,
    totals_by_currency: dict[str, Decimal],
    economic_allocation: dict[str, dict[EconomicAssetClass, Decimal]],
) -> JolikaStructuralDiversification:
    """Measure diversification by asset and economic class using HHI."""

    asset_hhi_values: list[Decimal] = []
    for currency, total in sorted(totals_by_currency.items()):
        if total <= 0:
            continue
        weights = [
            position.market_value / total
            for position in portfolio.positions
            if position.currency == currency
        ]
        asset_hhi_values.append(
            sum((weight * weight for weight in weights), Decimal("0"))
        )

    class_hhi_values: list[Decimal] = []
    for currency, allocation in sorted(economic_allocation.items()):
        total = totals_by_currency.get(currency, Decimal("0"))
        if total <= 0:
            continue
        weights = [
            value / total
            for value in allocation.values()
        ]
        class_hhi_values.append(
            sum((weight * weight for weight in weights), Decimal("0"))
        )

    asset_hhi = max(asset_hhi_values, default=Decimal("0"))
    class_hhi = max(class_hhi_values, default=Decimal("0"))
    structural_hhi = max(asset_hhi, class_hhi)

    if structural_hhi <= Decimal("0.25"):
        return JolikaStructuralDiversification(
            level="Alta",
            asset_hhi=asset_hhi,
            class_hhi=class_hhi,
            driver=None,
        )

    if structural_hhi <= Decimal("0.50"):
        return JolikaStructuralDiversification(
            level="Média",
            asset_hhi=asset_hhi,
            class_hhi=class_hhi,
            driver="asset_and_class_concentration",
        )

    return JolikaStructuralDiversification(
        level="Baixa",
        asset_hhi=asset_hhi,
        class_hhi=class_hhi,
        driver="asset_and_class_concentration",
    )


def build_jolika_portfolio_intelligence(
    positions: Iterable[PortfolioPosition],
    *,
    top_n: int = 10,
) -> JolikaPortfolioIntelligence:
    """Build deterministic factual intelligence for JOLIKA positions."""

    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")

    canonical_positions = tuple(positions)

    for position in canonical_positions:
        if position.owner is not PortfolioOwner.JOLIKA:
            raise ValueError("all positions must belong to JOLIKA")

    consolidated = PortfolioConsolidationEngine().consolidate(
        canonical_positions
    )

    totals = _totals_by_currency(consolidated)
    allocation = _economic_allocation_by_currency(consolidated)
    concentration = _concentration(
        consolidated,
        totals,
        top_n=top_n,
    )
    coverage = _coverage(consolidated)
    duplicates = _duplicates(consolidated)

    institutions = tuple(
        sorted(
            {
                origin.institution
                for position in consolidated.positions
                for origin in position.origins
            }
        )
    )

    source_files = tuple(
        sorted(
            {
                origin.source_file
                for position in consolidated.positions
                for origin in position.origins
            }
        )
    )

    return JolikaPortfolioIntelligence(
        owner=PortfolioOwner.JOLIKA,
        original_position_count=(
            consolidated.report.statistics.original_positions
        ),
        consolidated_asset_count=len(consolidated.positions),
        institutions=institutions,
        currencies=tuple(sorted(totals)),
        totals_by_currency=_freeze_totals(totals),
        economic_allocation_by_currency=(
            _freeze_economic_allocation(allocation)
        ),
        concentration_by_currency=concentration,
        coverage=coverage,
        duplicate_exposures=duplicates,
        consolidation_alerts=consolidated.report.alerts,
        priority=_priority(
            concentration,
            coverage,
            duplicates,
        ),
        materiality=_materiality(concentration),
        diversification=_diversification(
            consolidated,
            totals,
            allocation,
        ),
        source_files=source_files,
    )
