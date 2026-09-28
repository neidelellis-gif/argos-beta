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

    # Macro facts are portfolio-level context by nature. Rank official macro
    # evidence first so the limited Stage 4 slots are not consumed by input order.
    macro_facts = sorted(
        (
            fact for fact in fact_items
            if fact.id not in seen_fact_ids and fact.category is FactCategory.ECONOMY
        ),
        key=_macro_rank_key,
    )
    for fact in macro_facts:
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


def _macro_rank_key(fact: FactCandidate) -> tuple[object, ...]:
    source_rank = {"Federal Reserve": 0, "BLS": 1, "BEA": 2}.get(fact.source, 3)
    importance_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(
        fact.importance.value, 4
    )
    return (source_rank, importance_rank, -fact.published_at.timestamp(), fact.title.casefold())


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
    if item.source in {"Federal Reserve", "BLS", "BEA"}:
        return "Macro e juros"
    if item.source == "Google News":
        return "Mercados"
    text = f"{item.title} {item.evidence}".casefold()
    if any(term in text for term in ("fomc", "federal reserve", "interest rate", "inflation", "cpi", "yield")):
        return "Macro e juros"
    if any(term in text for term in ("sec ", "regulation", "regulatory", "rule", "approval")):
        return "Eventos relevantes"
    if any(term in text for term in ("bitcoin", "ethereum", "crypto", "ai ", "semiconductor", "chip", "energy", "infrastructure")):
        return "Temas e teses"
    return "Mercados"



def _portfolio_exposure_classes(positions: Iterable[PortfolioPosition]) -> tuple[str, ...]:
    labels: list[str] = []
    for position in positions:
        raw = " ".join(
            value for value in (
                position.asset_class,
                position.asset_subclass,
                position.asset_name,
                position.identifier,
            )
            if value
        ).casefold()
        if any(term in raw for term in ("fixed income", "renda fixa", "bond", "treasury", "credit", "note")):
            label = "Renda fixa"
        elif any(term in raw for term in ("gold", "ouro", "commodity", "commodities")):
            label = "Ouro/Commodities"
        elif any(term in raw for term in ("bitcoin", "ethereum", "crypto", "cripto")):
            label = "Cripto"
        elif any(term in raw for term in ("cash", "caixa", "money market")):
            label = "Caixa"
        elif "etf" in raw:
            label = "ETFs"
        elif any(term in raw for term in ("fund", "fundo", "strategy", "estratégia")):
            label = "Fundos/Estratégias"
        elif any(term in raw for term in ("equity", "stock", "ação", "acoes", "ações")):
            label = "Ações"
        else:
            continue
        if label not in labels:
            labels.append(label)
    return tuple(labels)


def _macro_relevant_classes(item: JolikaMarketContextItem) -> tuple[str, ...]:
    text = f"{item.title} {item.evidence}".casefold()
    if item.source == "Federal Reserve" or any(
        term in text for term in ("fomc", "monetary policy", "interest rate", "discount rate")
    ):
        return ("Renda fixa", "Caixa", "Ações", "ETFs", "Fundos/Estratégias", "Ouro/Commodities")
    if item.source == "BLS" and any(
        term in text for term in ("consumer price", "cpi", "inflation")
    ):
        return ("Renda fixa", "Caixa", "Ações", "ETFs", "Ouro/Commodities")
    if item.source == "BLS" and any(
        term in text for term in ("unemployment", "nonfarm payroll", "employment")
    ):
        return ("Renda fixa", "Ações", "ETFs", "Fundos/Estratégias")
    if item.source == "BEA" and any(
        term in text for term in ("gross domestic product", "gdp", "personal income", "personal consumption")
    ):
        return ("Renda fixa", "Ações", "ETFs", "Fundos/Estratégias")
    return ()


def _executive_summary(item: JolikaMarketContextItem) -> str:
    text = f"{item.title} {item.evidence}".casefold()

    if item.source == "Federal Reserve":
        if "economic projection" in text or "economic projections" in text:
            return "O Federal Reserve divulgou novas projeções econômicas após a reunião do FOMC."
        if "fomc statement" in text or "monetary policy" in text:
            return "O Federal Reserve divulgou uma atualização oficial de política monetária do FOMC."
        return "O Federal Reserve divulgou uma atualização oficial relevante para o ambiente macroeconômico."

    if item.source == "BLS":
        if "consumer price" in text or "cpi" in text or "inflation" in text:
            return "O BLS divulgou o dado mais recente de inflação ao consumidor dos Estados Unidos."
        if "unemployment" in text:
            return "O BLS divulgou a taxa de desemprego mais recente dos Estados Unidos."
        if "nonfarm payroll" in text or "employment" in text:
            return "O BLS divulgou os dados mais recentes de emprego dos Estados Unidos."
        return "O BLS divulgou uma atualização oficial do mercado de trabalho e preços dos Estados Unidos."

    if item.source == "BEA":
        if "gross domestic product" in text or "gdp" in text:
            return "O BEA divulgou a atualização mais recente do PIB dos Estados Unidos."
        if "personal income" in text or "personal consumption" in text:
            return "O BEA divulgou a atualização mais recente de renda e consumo nos Estados Unidos."
        if "international trade" in text:
            return "O BEA divulgou uma atualização oficial sobre o comércio internacional dos Estados Unidos."
        return "O BEA divulgou uma atualização oficial relevante para o ambiente econômico dos Estados Unidos."

    if item.source == "Google News":
        if item.affected_assets:
            return (
                "Foi identificada uma notícia de mercado diretamente relacionada a "
                + ", ".join(item.affected_assets[:3])
                + "."
            )
        return "Foi identificada uma notícia de mercado potencialmente relevante para a carteira."

    return item.title.rstrip(".") + "."


def _evidence_lines(items: Iterable[JolikaMarketContextItem]) -> tuple[str, ...]:
    selected = tuple(items)[:2]
    sources: list[str] = []
    details: list[str] = []
    seen_details: set[str] = set()

    for item in selected:
        if item.source not in sources:
            sources.append(item.source)
        detail = item.evidence.strip()
        normalized = detail.casefold()
        if detail and normalized not in seen_details:
            seen_details.add(normalized)
            details.append(detail)

    lines: list[str] = []
    if sources:
        lines.append("Fonte: " + ", ".join(sources))
    lines.extend(details)
    return tuple(lines)


def _macro_exposure_text(
    positions: Iterable[PortfolioPosition],
    item: JolikaMarketContextItem,
) -> str:
    classes = _portfolio_exposure_classes(positions)
    relevant = _macro_relevant_classes(item)
    if relevant:
        classes = tuple(label for label in classes if label in relevant)
    else:
        classes = ()
    if not classes:
        return "Impacto tratado no nível de ambiente da carteira, sem atribuição automática a cada posição."
    return (
        "Exposições da carteira para acompanhamento deste contexto: "
        + ", ".join(classes)
        + ". A relação é de monitoramento; a direção do impacto não é inferida automaticamente."
    )


def build_market_context_stage(
    positions: Iterable[PortfolioPosition],
    facts: Iterable[FactCandidate],
) -> PatrimonialAnalysisStage:
    """Build Stage 4 from canonical facts and actual portfolio exposures."""

    position_items = tuple(positions)
    items = analyze_jolika_market_context(position_items, facts)
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
            else _macro_exposure_text(position_items, primary)
        )
        report_items.append(
            PatrimonialAnalysisItem(
                title=bucket,
                reading=(
                    f"{_executive_summary(primary)} {exposure_text} "
                    f"Relevância/intensidade: {primary.intensity}. "
                    f"Direção do impacto: {primary.impact_direction}."
                ),
                evidence=_evidence_lines(bucket_items),
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
