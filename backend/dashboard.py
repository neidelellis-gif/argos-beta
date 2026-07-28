"""Operational dashboard assembled from normalized portfolio diagnostics."""

from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, Optional

from backend.models import PortfolioPosition
from backend.portfolio_consolidation import consolidate_portfolio_positions
from backend.portfolio_diagnostics import (
    InstitutionDiagnostic,
    diagnose_consolidated,
    diagnose_institution,
)

DASHBOARD_VERSION = "1.0"
SIMULATED_FACTS = (
    "Dashboard operacional conectado à infraestrutura ARGOS.",
    "Fontes externas ainda não estão integradas.",
)


def _decimal_totals(totals: Dict[str, Decimal]) -> Dict[str, str]:
    """Serialize monetary totals without losing decimal precision."""
    return {
        currency: str(value)
        for currency, value in sorted(totals.items())
    }


def _institution_payload(diagnostic: InstitutionDiagnostic) -> Dict:
    return {
        "name": diagnostic.institution,
        "position_count": diagnostic.position_count,
        "currencies": list(diagnostic.currencies),
        "totals_by_currency": _decimal_totals(
            diagnostic.market_value_by_currency
        ),
        "warnings": list(diagnostic.data_quality_warnings),
    }


def build_dashboard(
    positions: Iterable[PortfolioPosition],
    current_date: Optional[date] = None,
) -> Dict:
    """Build one dashboard response from positions already normalized to MPU."""
    consolidation = consolidate_portfolio_positions(positions)
    institution_diagnostics = tuple(
        diagnose_institution(institution_positions)
        for _, institution_positions in sorted(
            consolidation.positions_by_institution.items()
        )
    )
    consolidated = diagnose_consolidated(institution_diagnostics)

    return {
        "header": {
            "current_date": (current_date or date.today()).isoformat(),
            "version": DASHBOARD_VERSION,
        },
        "important_facts": list(SIMULATED_FACTS),
        "institutions": [
            _institution_payload(diagnostic)
            for diagnostic in institution_diagnostics
        ],
        "consolidated": {
            "institution_count": len(consolidated.institutions),
            "position_count": consolidated.total_positions,
            "unique_asset_count": consolidated.unique_asset_count,
            "repeated_asset_count": consolidated.repeated_asset_count,
            "totals_by_currency": _decimal_totals(
                consolidated.totals_by_currency
            ),
            "warnings": list(consolidated.consolidated_warnings),
        },
    }


def load_dashboard() -> Dict:
    """Return the dashboard for currently available normalized positions."""
    return build_dashboard(())
