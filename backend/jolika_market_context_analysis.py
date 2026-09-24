"""Evidence-based Stage 4 market-context analysis for JOLIKA.

This module deliberately does not infer market direction from headlines. It
relates canonical market facts to real portfolio exposures and publishes only
what the supplied evidence supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.daily_facts_engine import DailyFactsEngine
from backend.important_facts import FactCandidate
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
    for relation in relevant:
        fact = facts_by_id.get(str(relation["id"]))
        if fact is None:
            continue
        priority = str(relation["priority"])
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
    return tuple(items)


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

    report_items = tuple(
        PatrimonialAnalysisItem(
            title=item.title,
            reading=(
                f"Exposições afetadas: {', '.join(item.affected_assets)}. "
                f"Relevância/intensidade: {item.intensity}. "
                f"Direção do impacto: {item.impact_direction}."
            ),
            evidence=(f"Fonte: {item.source}", item.evidence),
            confidence="Média",
        )
        for item in items
    )
    return PatrimonialAnalysisStage(
        key="market_context",
        title="Carteira × ambiente de mercado",
        summary=(
            f"{len(report_items)} fato(s) atual(is) possuem relação material com "
            "as exposições analisadas. A direção do impacto permanece não "
            "determinada quando a evidência disponível não sustenta essa conclusão."
        ),
        items=report_items,
        status="available",
    )
