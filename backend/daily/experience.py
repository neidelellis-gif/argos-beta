"""Assembly of the ARGOS daily experience from market context."""

from datetime import date, datetime
from typing import Dict, Iterable, Optional

from backend.daily.context_service import DailyContextService, PRIORITY_LEVELS
from backend.models import PortfolioPosition

PANORAMA_TOPICS = (
    "Macroeconomia",
    "Mercados",
    "Geopolítica",
    "Tecnologia",
    "Criptoativos",
)


def build_priorities(facts):
    """Project the first prioritized facts onto the existing Daily contract."""
    return [
        {
            "id": fact["id"],
            "title": fact["title"],
            "level": fact["priority"],
            "context": fact["context"],
        }
        for fact in facts[:3]
    ]


def build_daily_experience(
    positions: Iterable[PortfolioPosition],
    current_date: Optional[date] = None,
    now: Optional[datetime] = None,
    context_service: Optional[DailyContextService] = None,
) -> Dict:
    """Build the existing UI contract from prioritized market facts."""
    normalized_positions = tuple(positions)
    context = (context_service or DailyContextService()).generate(
        normalized_positions,
        now=now,
    )
    facts = context["facts"]
    priorities = build_priorities(facts)
    analyses = [
        {
            "id": fact["id"],
            "title": fact["title"],
            "reason": fact["summary"],
            "related_to": ", ".join(fact["matched_portfolio_assets"]) or None,
            "status": fact["context"],
            "updated_at": fact["occurred_at"],
        }
        for fact in facts
        if fact["context_type"] in {"portfolio", "macro"}
    ][:3]
    panorama = []
    for topic in PANORAMA_TOPICS:
        topic_fact = next((fact for fact in facts if fact["category"] == topic), None)
        panorama.append({
            "topic": topic,
            "status": "Atualizado" if topic_fact else "Sem fatos relevantes",
            "summary": topic_fact["summary"] if topic_fact else (
                "Nenhum fato relevante identificado nas últimas 24 horas."
            ),
        })

    return {
        "generated_for": (current_date or date.today()).isoformat(),
        "generated_at": context["generated_at"],
        "lookback_hours": context["lookback_hours"],
        "context_scope": "portfolio" if context["has_portfolio_context"] else "general",
        "important_facts": facts,
        "priorities": priorities,
        "analyses": analyses,
        "global_overview": panorama,
        "market_agenda": context["agenda"],
        "sources": context["sources"],
        "empty_states": {
            "important_facts": (
                "Fonte externa indisponível. O último contexto válido será "
                "reutilizado automaticamente quando existir."
                if context["sources"]["facts"]["status"] == "unavailable"
                else "Nenhum fato relevante identificado nas últimas 24 horas."
            ),
            "market_agenda": "Nenhum evento relevante previsto.",
        },
        "contracts": {
            "priority_levels": list(PRIORITY_LEVELS),
            "panorama_topics": list(PANORAMA_TOPICS),
            "agenda_event_types": [
                "Resultados",
                "Bancos centrais",
                "Inflação",
                "Emprego",
                "PIB",
                "Dividendos",
                "Vencimentos",
            ],
        },
    }
