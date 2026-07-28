"""Operational dashboard assembled from normalized portfolio diagnostics."""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Iterable, Optional

from backend.models import PortfolioPosition
from backend.portfolio_consolidation import consolidate_portfolio_positions
from backend.portfolio_diagnostics import (
    InstitutionDiagnostic,
    diagnose_consolidated,
    diagnose_institution,
)

DASHBOARD_VERSION = "2.1"


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
    last_import_at: Optional[datetime] = None,
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

    institution_count = len(consolidated.institutions)
    position_count = consolidated.total_positions
    institution_names = list(consolidated.institutions)
    has_import = last_import_at is not None
    institution_label = (
        "instituição" if institution_count == 1 else "instituições"
    )

    if has_import:
        portfolio_message = (
            f"{institution_count} {institution_label} analisada"
            if institution_count == 1
            else f"{institution_count} {institution_label} analisadas"
        )
        daily_situation = [
            {"status": "completed", "message": portfolio_message},
            {"status": "completed", "message": "Consolidação disponível"},
            {"status": "completed", "message": "Diagnósticos concluídos"},
        ]
    else:
        portfolio_message = "Nenhuma carteira carregada"
        daily_situation = [
            {"status": "waiting", "message": portfolio_message}
        ]

    modules = [
        {
            "id": "portfolios",
            "title": "Carteiras",
            "status": "completed" if has_import else "waiting",
            "message": portfolio_message,
        },
        {
            "id": "overview",
            "title": "Panorama",
            "status": "waiting",
            "message": "Aguardando inteligência de mercado",
        },
        {
            "id": "agenda",
            "title": "Agenda",
            "status": "waiting",
            "message": "Aguardando calendário",
        },
        {
            "id": "market",
            "title": "Mercado",
            "status": "waiting",
            "message": "Aguardando integração",
        },
    ]

    return {
        "header": {
            "current_date": (current_date or date.today()).isoformat(),
            "version": DASHBOARD_VERSION,
        },
        "labels": {
            "last_update": "Última importação",
            "overview": "Panorama",
            "overview_title": "Estado da integração de panorama",
            "daily_situation": "Situação do Dia",
            "daily_situation_title": "Estado operacional da sessão",
            "modules": "Módulos",
            "modules_title": "Status dos módulos",
        },
        "session": {
            "last_import_at": (
                last_import_at.isoformat() if last_import_at else None
            ),
            "institution_count": institution_count,
            "position_count": position_count,
            "analyzed_institutions": institution_names,
            "status": "active" if has_import else "waiting_import",
        },
        "daily_situation": daily_situation,
        "modules": modules,
        "important_facts": [item["message"] for item in daily_situation],
        "institutions": [
            _institution_payload(diagnostic)
            for diagnostic in institution_diagnostics
        ],
        "consolidated": {
            "institution_count": institution_count,
            "position_count": position_count,
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
