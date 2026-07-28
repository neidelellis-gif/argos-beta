"""Data-quality diagnostics for portfolios already normalized to the MPU."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, Optional, Tuple

from backend.models import PortfolioPosition


@dataclass(frozen=True)
class InstitutionDiagnostic:
    """Diagnostic facts for one institution, without investment analysis."""

    institution: Optional[str]
    position_count: int
    currencies: Tuple[str, ...]
    market_value_by_currency: Dict[str, Decimal]
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
    weights: Dict[str, Decimal] = {}
    missing_symbols = []
    missing_values = []
    symbol_counts: Dict[str, int] = {}
    warnings = []

    for position in institution_positions:
        if position.currency:
            currencies.add(position.currency)
            if position.market_value is not None:
                market_values[position.currency] = (
                    market_values.get(position.currency, Decimal("0"))
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
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

        if position.market_value is None:
            missing_values.append(_asset_label(position))

    duplicates = {
        symbol: count for symbol, count in symbol_counts.items() if count > 1
    }
    if missing_symbols:
        warnings.append(f"{len(missing_symbols)} position(s) without symbol")
    if missing_values:
        warnings.append(f"{len(missing_values)} position(s) without market value")
    if duplicates:
        warnings.append(f"{len(duplicates)} duplicated asset(s)")

    return InstitutionDiagnostic(
        institution=institution,
        position_count=len(institution_positions),
        currencies=tuple(sorted(currencies)),
        market_value_by_currency=market_values,
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
    institutions_by_asset: Dict[str, set] = {}
    warnings = []

    for diagnostic in institution_diagnostics:
        for currency, value in diagnostic.market_value_by_currency.items():
            totals[currency] = totals.get(currency, Decimal("0")) + value
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
        unique_asset_count=len(institutions_by_asset),
        repeated_asset_count=repeated_assets,
        consolidated_warnings=tuple(warnings),
    )
