"""Contracts and mock-backed assembly for the ARGOS daily experience."""

from datetime import date, datetime
from typing import Dict, Iterable, Optional, Sequence

from backend.models import PortfolioPosition

PRIORITY_LEVELS = ("Alta", "Moderada", "Baixa")
PANORAMA_TOPICS = (
    "Macroeconomia",
    "Mercados",
    "Geopolítica",
    "Tecnologia",
    "Criptoativos",
)


def _portfolio_context(
    positions: Sequence[PortfolioPosition],
    last_import_at: Optional[datetime],
) -> Dict:
    institutions = sorted({position.institution for position in positions})
    if not positions:
        return {
            "fact": {
                "id": "portfolio-waiting",
                "title": "Carteiras aguardam atualização",
                "category": "Carteiras",
                "priority": "Alta",
                "summary": (
                    "Importe as posições para habilitar o contexto patrimonial "
                    "do dia."
                ),
            },
            "priority": {
                "id": "update-portfolios",
                "title": "Atualizar as carteiras",
                "level": "Alta",
                "context": "Nenhuma posição oficial está disponível nesta sessão.",
            },
            "analysis": {
                "id": "portfolio-analysis-waiting",
                "title": "Diagnóstico patrimonial pendente",
                "reason": "A análise depende da importação das posições atuais.",
                "related_to": None,
                "status": "Aguardando dados",
            },
        }

    institution_label = ", ".join(institutions)
    imported = last_import_at.isoformat() if last_import_at else None
    return {
        "fact": {
            "id": "portfolio-ready",
            "title": "Contexto das carteiras atualizado",
            "category": "Carteiras",
            "priority": "Moderada",
            "summary": (
                f"{len(positions)} posições de {institution_label} estão "
                "disponíveis para análise."
            ),
        },
        "priority": {
            "id": "review-diagnostics",
            "title": "Revisar diagnósticos das carteiras",
            "level": "Moderada",
            "context": "Os dados importados já estão consolidados no dashboard.",
        },
        "analysis": {
            "id": "portfolio-diagnostics",
            "title": "Diagnósticos das posições importadas",
            "reason": "Há dados oficiais disponíveis para revisão executiva.",
            "related_to": institution_label,
            "status": "Disponível",
            "updated_at": imported,
        },
    }


def build_daily_experience(
    positions: Iterable[PortfolioPosition],
    current_date: Optional[date] = None,
    last_import_at: Optional[datetime] = None,
) -> Dict:
    """Build the daily contract, using mocks where integrations do not exist."""
    normalized_positions = tuple(positions)
    context = _portfolio_context(normalized_positions, last_import_at)

    return {
        "generated_for": (current_date or date.today()).isoformat(),
        "lookback_hours": 24,
        "important_facts": [
            context["fact"],
            {
                "id": "market-intelligence-waiting",
                "title": "Inteligência externa ainda não conectada",
                "category": "Mercados",
                "priority": "Baixa",
                "summary": (
                    "O bloco está preparado para receber fatos rastreáveis "
                    "das últimas 24 horas."
                ),
            },
        ],
        "priorities": [context["priority"]],
        "analyses": [context["analysis"]],
        "global_overview": [
            {
                "topic": topic,
                "status": "Aguardando integração",
                "summary": "Nenhuma informação oficial disponível no momento.",
            }
            for topic in PANORAMA_TOPICS
        ],
        "market_agenda": [],
        "empty_states": {
            "market_agenda": (
                "Nenhum evento de mercado disponível. A integração de "
                "calendário será adicionada em etapa futura."
            )
        },
        "contracts": {
            "priority_levels": list(PRIORITY_LEVELS),
            "panorama_topics": list(PANORAMA_TOPICS),
            "agenda_event_types": [
                "Resultados",
                "Bancos centrais",
                "Inflação",
                "Emprego",
                "Dividendos",
                "Vencimentos",
            ],
        },
    }
