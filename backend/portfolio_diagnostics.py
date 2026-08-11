"""Data-quality diagnostics for portfolios already normalized to the MPU."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, Optional, Tuple

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition

EconomicAllocation = Dict[str, Dict[EconomicAssetClass, Decimal]]


@dataclass(frozen=True)
class InstitutionDiagnostic:
    """Diagnostic facts for one institution, without investment analysis."""

    institution: Optional[str]
    position_count: int
    currencies: Tuple[str, ...]
    market_value_by_currency: Dict[str, Decimal]
    economic_allocation_by_currency: EconomicAllocation
    total_weight_by_currency: Dict[str, Decimal]
    assets_without_symbol: Tuple[str, ...]
    assets_without_market_value: Tuple[str, ...]
    duplicate_assets: Dict[str, int]
    data_quality_warnings: Tuple[str, ...]
    asset_symbols: Tuple[str, ...]


@dataclass(frozen=True)
class ConsolidatedDiagnostic:
    """Consolidation composed exclusively from institution diagnostics."""

    institutions: Tuple[str, ...]
    total_positions: int
    totals_by_currency: Dict[str, Decimal]
    economic_allocation_by_currency: EconomicAllocation
    unique_asset_count: int
    repeated_asset_count: int
    consolidated_warnings: Tuple[str, ...]


def _asset_label(position: PortfolioPosition) -> str:
    """Return a stable human-readable label for data-quality messages."""
    return position.asset_name or position.identifier or "<unnamed asset>"


def _normalized_symbol(position: PortfolioPosition) -> Optional[str]:
    """Use the MPU identifier as its asset symbol, ignoring blank values."""
    if position.identifier is None:
        return None
    symbol = position.identifier.strip()
    return symbol.upper() if symbol else None


def _duplicate_key(position: PortfolioPosition) -> Optional[str]:
    symbol = _normalized_symbol(position)
    if symbol is None:
        return None
    is_cash = position.economic_asset_class is EconomicAssetClass.CASH or (
        position.economic_asset_class is None
        and (position.asset_class or "").strip().upper() == "CAIXA"
    )
    if not is_cash:
        return symbol

    account = (position.account or "").strip().upper()
    currency = (position.currency or "").strip().upper()
    asset_label = symbol or _asset_label(position).strip().upper()
    return "|".join((position.institution.strip().upper(), account, currency, asset_label))


def diagnose_institution(
    positions: Iterable[PortfolioPosition],
) -> InstitutionDiagnostic:
    """Diagnose positions from exactly one institution using only MPU fields."""
    institution_positions = tuple(positions)
    institutions = {position.institution for position in institution_positions}
    if len(institutions) > 1:
        raise ValueError(
            "diagnose_institution accepts positions from only one institution"
        )

    institution = next(iter(institutions), None)
    currencies = set()
    market_values: Dict[str, Decimal] = {}
    economic_allocation: EconomicAllocation = {}
    weights: Dict[str, Decimal] = {}
    missing_symbols = []
    missing_values = []
    symbol_counts: Dict[str, int] = {}
    warnings = []
    missing_economic_class = 0

    for position in institution_positions:
        if position.currency:
            currencies.add(position.currency)
            if position.market_value is not None:
                market_values[position.currency] = (
                    market_values.get(position.currency, Decimal("0"))
                    + position.market_value
                )
                if position.economic_asset_class is not None:
                    currency_allocation = economic_allocation.setdefault(
                        position.currency, {}
                    )
                    economic_class = position.economic_asset_class
                    currency_allocation[economic_class] = (
                        currency_allocation.get(economic_class, Decimal("0"))
                        + position.market_value
                    )
            if position.portfolio_weight is not None:
                weights[position.currency] = (
                    weights.get(position.currency, Decimal("0"))
                    + position.portfolio_weight
                )
        elif position.market_value is not None or position.portfolio_weight is not None:
            warnings.append(
                f"{_asset_label(position)} has value or weight without currency"
            )

        symbol = _normalized_symbol(position)
        if symbol is None:
            missing_symbols.append(_asset_label(position))
        else:
            duplicate_key = _duplicate_key(position)
            if duplicate_key is not None:
                symbol_counts[duplicate_key] = symbol_counts.get(duplicate_key, 0) + 1

        if position.market_value is None:
            missing_values.append(_asset_label(position))
        if (
            position.owner is PortfolioOwner.JOLIKA
            and position.economic_asset_class is None
        ):
            missing_economic_class += 1

    duplicates = {
        symbol: count for symbol, count in symbol_counts.items() if count > 1
    }
    if missing_symbols:
        warnings.append(f"{len(missing_symbols)} position(s) without symbol")
    if missing_values:
        warnings.append(f"{len(missing_values)} position(s) without market value")
    if duplicates:
        warnings.append(f"{len(duplicates)} duplicated asset(s)")
    if missing_economic_class:
        warnings.append(
            f"{missing_economic_class} JOLIKA position(s) without economic asset class"
        )

    return InstitutionDiagnostic(
        institution=institution,
        position_count=len(institution_positions),
        currencies=tuple(sorted(currencies)),
        market_value_by_currency=market_values,
        economic_allocation_by_currency=economic_allocation,
        total_weight_by_currency=weights,
        assets_without_symbol=tuple(missing_symbols),
        assets_without_market_value=tuple(missing_values),
        duplicate_assets=duplicates,
        data_quality_warnings=tuple(warnings),
        asset_symbols=tuple(symbol_counts),
    )


def diagnose_consolidated(
    diagnostics: Iterable[InstitutionDiagnostic],
) -> ConsolidatedDiagnostic:
    """Consolidate previously calculated institution diagnostics."""
    institution_diagnostics = tuple(diagnostics)
    present_institutions = tuple(
        sorted(
            diagnostic.institution
            for diagnostic in institution_diagnostics
            if diagnostic.institution is not None
        )
    )
    totals: Dict[str, Decimal] = {}
    economic_allocation: EconomicAllocation = {}
    institutions_by_asset: Dict[str, set[Optional[str]]] = {}
    warnings: list[str] = []

    for diagnostic in institution_diagnostics:
        for currency, value in diagnostic.market_value_by_currency.items():
            totals[currency] = totals.get(currency, Decimal("0")) + value
        for currency, allocation in diagnostic.economic_allocation_by_currency.items():
            consolidated_currency = economic_allocation.setdefault(currency, {})
            for economic_class, value in allocation.items():
                consolidated_currency[economic_class] = (
                    consolidated_currency.get(economic_class, Decimal("0")) + value
                )
        for symbol in diagnostic.asset_symbols:
            institutions_by_asset.setdefault(symbol, set()).add(
                diagnostic.institution
            )
        prefix = diagnostic.institution or "unknown institution"
        warnings.extend(
            f"{prefix}: {warning}"
            for warning in diagnostic.data_quality_warnings
        )

    repeated_assets = sum(
        len(institutions) > 1 for institutions in institutions_by_asset.values()
    )
    return ConsolidatedDiagnostic(
        institutions=present_institutions,
        total_positions=sum(
            diagnostic.position_count for diagnostic in institution_diagnostics
        ),
        totals_by_currency=totals,
        economic_allocation_by_currency=economic_allocation,
        unique_asset_count=len(institutions_by_asset),
        repeated_asset_count=repeated_assets,
        consolidated_warnings=tuple(warnings),
    )
