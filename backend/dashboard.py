"""Operational dashboard assembled from normalized portfolio diagnostics."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, Iterable, Optional

from backend.daily.orchestrator import DailyOrchestrator
from backend.jolika_portfolio_intelligence import build_jolika_portfolio_intelligence
from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_consolidation import consolidate_portfolio_positions
from backend.portfolio_diagnostics import (
    InstitutionDiagnostic,
    diagnose_consolidated,
    diagnose_institution,
)

DASHBOARD_VERSION = "2.3"


def _decimal_totals(totals: Dict[str, Decimal]) -> Dict[str, str]:
    """Serialize monetary totals without losing decimal precision."""
    return {
        currency: str(value)
        for currency, value in sorted(totals.items())
    }


def _economic_allocation(
    allocation: Dict[str, Dict[EconomicAssetClass, Decimal]],
) -> Dict[str, Dict[str, str]]:
    """Serialize currency-safe economic allocations deterministically."""
    return {
        currency: {
            economic_class.value: str(value)
            for economic_class, value in sorted(
                values.items(), key=lambda item: item[0].value
            )
        }
        for currency, values in sorted(allocation.items())
    }


def _institution_payload(diagnostic: InstitutionDiagnostic) -> Dict:
    return {
        "name": diagnostic.institution,
        "position_count": diagnostic.position_count,
        "currencies": list(diagnostic.currencies),
        "totals_by_currency": _decimal_totals(
            diagnostic.market_value_by_currency
        ),
        "economic_allocation_by_currency": _economic_allocation(
            diagnostic.economic_allocation_by_currency
        ),
        "warnings": list(diagnostic.data_quality_warnings),
    }


def _jolika_intelligence_payload(positions: Iterable[PortfolioPosition]) -> Dict:
    intelligence = build_jolika_portfolio_intelligence(positions)

    return {
        "original_position_count": intelligence.original_position_count,
        "consolidated_asset_count": intelligence.consolidated_asset_count,
        "institutions": list(intelligence.institutions),
        "currencies": list(intelligence.currencies),
        "totals_by_currency": {
            currency: str(value)
            for currency, value in intelligence.totals_by_currency
        },
        "economic_allocation_by_currency": {
            currency: {
                economic_class.value: str(value)
                for economic_class, value in allocation
            }
            for currency, allocation in intelligence.economic_allocation_by_currency
        },
        "concentration_by_currency": [
            {
                "currency": concentration.currency,
                "total_market_value": str(concentration.total_market_value),
                "asset_count": concentration.asset_count,
                "top_positions": [
                    {
                        "asset_label": exposure.asset_label,
                        "identifier": exposure.identifier,
                        "currency": exposure.currency,
                        "market_value": str(exposure.market_value),
                        "weight_within_currency": (
                            str(exposure.weight_within_currency)
                            if exposure.weight_within_currency is not None
                            else None
                        ),
                        "institution_count": exposure.institution_count,
                        "institutions": list(exposure.institutions),
                    }
                    for exposure in concentration.top_positions
                ],
                "top_1_weight": (
                    str(concentration.top_1_weight)
                    if concentration.top_1_weight is not None
                    else None
                ),
                "top_3_weight": (
                    str(concentration.top_3_weight)
                    if concentration.top_3_weight is not None
                    else None
                ),
                "top_5_weight": (
                    str(concentration.top_5_weight)
                    if concentration.top_5_weight is not None
                    else None
                ),
            }
            for concentration in intelligence.concentration_by_currency
        ],
        "coverage": {
            "original_position_count": intelligence.coverage.original_position_count,
            "consolidated_asset_count": intelligence.coverage.consolidated_asset_count,
            "assets_with_economic_class": intelligence.coverage.assets_with_economic_class,
            "assets_without_economic_class": intelligence.coverage.assets_without_economic_class,
            "assets_with_identifier": intelligence.coverage.assets_with_identifier,
            "assets_without_identifier": intelligence.coverage.assets_without_identifier,
        },
        "duplicate_exposures": [
            {
                "asset_key": duplicate.asset_key,
                "institutions": list(duplicate.institutions),
                "within_same_institution": duplicate.within_same_institution,
                "across_institutions": duplicate.across_institutions,
                "source_position_count": duplicate.source_position_count,
            }
            for duplicate in intelligence.duplicate_exposures
        ],
        "consolidation_alerts": list(intelligence.consolidation_alerts),
        "priority": {
            "level": intelligence.priority.level,
            "reasons": list(intelligence.priority.reasons),
        },
        "materiality": {
            "level": intelligence.materiality.level,
            "max_position_weight": str(
                intelligence.materiality.max_position_weight
            ),
            "driver": intelligence.materiality.driver,
        },
        "diversification": {
            "level": intelligence.diversification.level,
            "asset_hhi": str(intelligence.diversification.asset_hhi),
            "class_hhi": str(intelligence.diversification.class_hhi),
            "driver": intelligence.diversification.driver,
        },
        "portfolio_reading": intelligence.portfolio_reading,
        "source_files": list(intelligence.source_files),
    }


def build_dashboard(
    positions: Iterable[PortfolioPosition],
    current_date: Optional[date] = None,
    last_import_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Dict:
    """Build one dashboard response from positions already normalized to MPU."""
    positions = tuple(positions)
    if any(position.owner is not PortfolioOwner.JOLIKA for position in positions):
        raise ValueError("JOLIKA dashboard accepts only JOLIKA portfolio positions")

    consolidation = consolidate_portfolio_positions(positions)

    institution_diagnostics = tuple(
        diagnose_institution(institution_positions)
        for _, institution_positions in sorted(
            consolidation.positions_by_institution.items()
        )
    )

    consolidated = diagnose_consolidated(institution_diagnostics)
    jolika_intelligence = _jolika_intelligence_payload(positions)

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

    daily = DailyOrchestrator().build(
        positions,
        current_date=current_date,
        now=now,
    )

    fact_status = daily["sources"]["facts"]["status"]
    agenda_status = daily["sources"]["agenda"]["status"]

    overview_module = {
        "id": "overview",
        "title": "Panorama",
        "status": "unavailable" if fact_status == "unavailable" else "completed",
        "message": (
            "Indisponível"
            if fact_status == "unavailable"
            else "Concluído"
            if fact_status == "available"
            else "Sem fatos relevantes"
        ),
    }

    modules = [
        {
            "id": "portfolios",
            "title": "Carteiras",
            "status": "completed" if has_import else "waiting",
            "message": portfolio_message,
        },
        overview_module,
        {
            "id": "agenda",
            "title": "Agenda",
            "status": "unavailable" if agenda_status == "unavailable" else "completed",
            "message": (
                "Indisponível"
                if agenda_status == "unavailable"
                else "Concluído"
                if agenda_status == "available"
                else "Sem eventos relevantes"
            ),
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
        "daily": daily,
        "labels": {
            "last_update": "Última importação",
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
            "economic_allocation_by_currency": _economic_allocation(
                consolidated.economic_allocation_by_currency
            ),
            "warnings": list(consolidated.consolidated_warnings),
            "intelligence": jolika_intelligence,
        },
    }


def load_dashboard() -> Dict:
    """Return the dashboard for currently available normalized positions."""
    from backend.official_portfolios import OfficialPortfolioLoader

    positions = OfficialPortfolioLoader().load_positions()
    reference = max(
        position.reference_date
        for position in positions
        if position.reference_date
    )

    return build_dashboard(
        positions,
        last_import_at=datetime.combine(
            reference,
            datetime.min.time(),
            timezone.utc,
        ),
    )
