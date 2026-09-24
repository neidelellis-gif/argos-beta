"""Evidence-based Stage 4 market-context analysis for JOLIKA.

This module deliberately does not infer market direction from headlines. It
relates canonical market facts to real portfolio exposures and publishes only
what the supplied evidence supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re

from backend.daily_facts_engine import DailyFactsEngine
from backend.important_facts import FactCandidate, FactCategory
from backend.models import PortfolioPosition
from backend.patrimonial_analysis_method import (
    PatrimonialAnalysisItem,
    PatrimonialAnalysisStage,
    unavailable_stage,
)


@dataclass(frozen=True)
class JolikaMarketContextItem:
    """One traceable relation between a market fact and portfolio exposure."""

    fact_id: str
    title: str
    affected_assets: tuple[str, ...]
    intensity: str
    source: str
    evidence: str
    impact_direction: str = "Não determinada"


_PRIORITY_INTENSITY = {
    "HIGH": "Alta",
    "MEDIUM": "Moderada",
    "LOW": "Baixa",
}


def analyze_jolika_market_context(
    positions: Iterable[PortfolioPosition],
    facts: Iterable[FactCandidate],
) -> tuple[JolikaMarketContextItem, ...]:
    """Relate canonical facts to positions without inventing impact direction."""

    position_items = tuple(positions)
    fact_items = tuple(facts)
    relevant = DailyFactsEngine().generate(position_items, fact_items)
    facts_by_id = {fact.id: fact for fact in fact_items}

    items: list[JolikaMarketContextItem] = []
    seen_topics: set[str] = set()
    seen_fact_ids: set[str] = set()
    for relation in relevant:
        fact = facts_by_id.get(str(relation["id"]))
        if fact is None:
            continue
        priority = str(relation["priority"])
        topic = _topic_key(fact)
        if topic in seen_topics:
            continue
        seen_topics.add(topic)
        seen_fact_ids.add(fact.id)
        items.append(
            JolikaMarketContextItem(
                fact_id=fact.id,
                title=fact.title,
                affected_assets=tuple(str(value) for value in relation["affected_assets"]),
                intensity=_PRIORITY_INTENSITY.get(priority, "Não determinada"),
                source=fact.source,
                evidence=fact.description,
            )
        )

    # Macro facts are portfolio-level context by nature. They must not be
    # discarded merely because they do not name an individual security.
    for fact in fact_items:
        if fact.id in seen_fact_ids or fact.category is not FactCategory.ECONOMY:
            continue
        topic = _topic_key(fact)
        if topic in seen_topics:
            continue
        seen_topics.add(topic)
        items.append(
            JolikaMarketContextItem(
                fact_id=fact.id,
                title=fact.title,
                affected_assets=(),
                intensity=_PRIORITY_INTENSITY.get(fact.importance.value, "Não determinada"),
                source=fact.source,
                evidence=fact.description,
            )
        )

    return tuple(items[:4])


def _topic_key(fact: FactCandidate) -> str:
    text = f"{fact.title} {fact.description}".casefold()
    text = re.sub(r"[^a-z0-9á-úç]+", " ", text)
    ignored = {
        "the", "and", "of", "to", "from", "for", "a", "an", "in",
        "board", "federal", "reserve", "release", "releases", "issues",
        "announces", "meeting", "committee",
    }
    tokens = [token for token in text.split() if token not in ignored]
    return " ".join(tokens[:8])


def _context_bucket(item: JolikaMarketContextItem) -> str:
    text = f"{item.title} {item.evidence}".casefold()
    if any(term in text for term in ("fomc", "federal reserve", "interest rate", "inflation", "cpi", "yield")):
        return "Macro e juros"
    if any(term in text for term in ("sec ", "regulation", "regulatory", "rule", "approval")):
        return "Eventos relevantes"
    if any(term in text for term in ("bitcoin", "ethereum", "crypto", "ai ", "semiconductor", "chip", "energy", "infrastructure")):
        return "Temas e teses"
    return "Mercados"


def build_market_context_stage(
    positions: Iterable[PortfolioPosition],
    facts: Iterable[FactCandidate],
) -> PatrimonialAnalysisStage:
    """Build Stage 4 from canonical facts and actual portfolio exposures."""

    items = analyze_jolika_market_context(positions, facts)
    if not items:
        return unavailable_stage(
            "market_context",
            "Carteira × ambiente de mercado",
            (
                "Não há fatos atuais e suficientemente relacionados às exposições "
                "analisadas para sustentar uma leitura de ambiente de mercado. "
                "O ARGOS não atribuirá direção de impacto sem evidência."
            ),
        )

    grouped: dict[str, list[JolikaMarketContextItem]] = {
        "Macro e juros": [],
        "Mercados": [],
        "Temas e teses": [],
        "Eventos relevantes": [],
    }
    for item in items:
        grouped[_context_bucket(item)].append(item)

    report_items: list[PatrimonialAnalysisItem] = []
    for bucket, bucket_items in grouped.items():
        if not bucket_items:
            continue
        primary = bucket_items[0]
        exposures = tuple(
            sorted(
                {
                    asset
                    for candidate in bucket_items
                    for asset in candidate.affected_assets
                },
                key=lambda value: (value.casefold(), value),
            )
        )
        exposure_text = (
            f"Exposições diretamente relacionadas: {', '.join(exposures[:5])}."
            if exposures
            else "Impacto tratado no nível de ambiente da carteira, sem atribuição automática a cada posição."
        )
        report_items.append(
            PatrimonialAnalysisItem(
                title=bucket,
                reading=(
                    f"{primary.title}. {exposure_text} "
                    f"Relevância/intensidade: {primary.intensity}. "
                    f"Direção do impacto: {primary.impact_direction}."
                ),
                evidence=tuple(
                    value
                    for candidate in bucket_items[:2]
                    for value in (f"Fonte: {candidate.source}", candidate.evidence)
                ),
                confidence="Média",
            )
        )

    return PatrimonialAnalysisStage(
        key="market_context",
        title="Carteira × ambiente de mercado",
        summary=(
            "Os fatos recentes foram consolidados nas quatro leituras de ambiente do ARGOS. "
            "Somente relações materiais com a carteira permanecem visíveis; fatos repetidos "
            "ou antigos são excluídos. A direção do impacto continua não determinada quando "
            "a evidência disponível não sustenta essa conclusão."
        ),
        items=tuple(report_items),
        status="available",
    )
