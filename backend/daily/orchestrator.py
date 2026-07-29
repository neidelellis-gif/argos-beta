"""Assembly of the standardized Daily structure."""

from datetime import date, datetime
from typing import Dict, Iterable, Optional

from backend.daily.context_service import DailyContextService, PRIORITY_LEVELS
from backend.daily.transformations import build_analyses, build_priorities
from backend.models import PortfolioPosition

PANORAMA_TOPICS = (
    "Macroeconomia",
    "Mercados",
    "Geopolítica",
    "Tecnologia",
    "Criptoativos",
)


class DailyOrchestrator:
    """Build the Daily contract without fetching or interpreting data."""

    def __init__(self, context_service=None):
        self._context_service = context_service or DailyContextService()

    def build(
        self,
        positions: Iterable[PortfolioPosition] = (),
        current_date: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> Dict:
        """Return the complete Daily contract populated from the official context."""
        normalized_positions = tuple(positions)
        context = self._context_service.generate(normalized_positions, now=now)
        facts = list(context["facts"])
        panorama = []
        for topic in PANORAMA_TOPICS:
            topic_fact = next(
                (fact for fact in facts if fact["category"] == topic),
                None,
            )
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
            "context_scope": (
                "portfolio" if context["has_portfolio_context"] else "general"
            ),
            "important_facts": facts,
            "priorities": build_priorities(facts),
            "analyses": build_analyses(facts),
            "global_overview": panorama,
            "market_agenda": list(context["agenda"]),
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
