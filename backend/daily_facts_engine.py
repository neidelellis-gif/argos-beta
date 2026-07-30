"""Portfolio-aware generation of objective daily fact candidates.

The engine is deliberately isolated from presentation and portfolio mutation.
It only relates structured, already available context to canonical positions.
"""

from collections.abc import Iterable
import re
import unicodedata

from backend.important_facts import FactCandidate, FactImportance
from backend.models import PortfolioPosition


_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_RECOMMENDATION_TERMS = re.compile(
    r"\b(comprar|vender|investir|desinvestir|aportar|resgatar|recomenda(?:r|ção)|"
    r"buy|sell|invest|recommend(?:ation)?)\b",
    re.IGNORECASE,
)


class DailyFactsEngine:
    """Relate known structured events to canonical portfolio positions."""

    max_facts = 5

    def generate(
        self,
        positions: Iterable[PortfolioPosition],
        context: Iterable[FactCandidate],
    ) -> list[dict[str, object]]:
        """Return relevant, independent facts ordered by official priority."""
        position_items = tuple(positions)
        context_items = tuple(context)
        if any(not isinstance(item, PortfolioPosition) for item in position_items):
            raise TypeError("positions accepts only PortfolioPosition instances")
        if any(not isinstance(item, FactCandidate) for item in context_items):
            raise TypeError("context accepts only FactCandidate instances")
        if not position_items:
            return []

        generated: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        seen_titles: set[str] = set()
        for event in context_items:
            affected = self._affected_assets(position_items, event)
            if not affected or self._contains_recommendation(event):
                continue
            event_id = self._normalize(event.id)
            title = self._normalize(event.title)
            if not event_id or not title or event_id in seen_ids or title in seen_titles:
                continue
            seen_ids.add(event_id)
            seen_titles.add(title)
            generated.append(
                {
                    "id": event.id,
                    "category": event.category.value,
                    "priority": self._priority(event.importance),
                    "title": event.title,
                    "summary": event.description,
                    "affected_assets": list(affected),
                }
            )

        generated.sort(
            key=lambda fact: (
                _PRIORITY_ORDER[str(fact["priority"])],
                str(fact["title"]).casefold(),
                str(fact["id"]).casefold(),
            )
        )
        return generated[: self.max_facts]

    # Naming compatible with the other daily engines.
    build = generate

    @classmethod
    def _affected_assets(
        cls, positions: tuple[PortfolioPosition, ...], event: FactCandidate
    ) -> tuple[str, ...]:
        relations = {
            cls._normalize(value)
            for values in (
                event.related_assets,
                event.related_sectors,
                event.related_currencies,
                event.related_institutions,
            )
            for value in values
            if value.strip()
        }
        if not relations:
            return ()

        affected: set[str] = set()
        for position in positions:
            terms = {
                cls._normalize(value)
                for value in (
                    position.identifier,
                    position.asset_name,
                    position.asset_class,
                    position.asset_subclass,
                    position.currency,
                    position.institution,
                )
                if value
            }
            if relations & terms:
                label = position.identifier or position.asset_name
                if label:
                    affected.add(label)
        return tuple(sorted(affected, key=lambda value: (value.casefold(), value)))

    @staticmethod
    def _priority(importance: FactImportance) -> str:
        return "HIGH" if importance is FactImportance.CRITICAL else importance.value

    @staticmethod
    def _contains_recommendation(event: FactCandidate) -> bool:
        return bool(_RECOMMENDATION_TERMS.search(f"{event.title} {event.description}"))

    @staticmethod
    def _normalize(value: str) -> str:
        plain = unicodedata.normalize("NFKD", value)
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()
