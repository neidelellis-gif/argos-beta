"""Operational intelligence for the JOLIKA portfolio held at Santander."""

from __future__ import annotations

from dataclasses import dataclass

from backend.models import PortfolioOwner
from backend.santander_portfolio_intelligence import (
    SantanderPortfolioIntelligence,
)
from backend.santander_quantitative_intelligence import (
    SantanderQuantitativeIntelligence,
)


@dataclass(frozen=True)
class SantanderOperationalAttention:
    """One factual reason for executive attention."""

    source: str
    level: str
    reason: str
    identifier: str | None = None
    asset_label: str | None = None


@dataclass(frozen=True)
class SantanderOperationalIntelligence:
    """Combined structural and quantitative reading for Santander/JOLIKA."""

    institution: str
    owner: PortfolioOwner

    structural_level: str
    quantitative_level: str
    overall_level: str

    attention_items: tuple[SantanderOperationalAttention, ...]

    analyzed_quantitative_positions: int
    unavailable_quantitative_positions: int

    executive_reading: str


_LEVEL_RANK = {
    "Baixa": 1,
    "Média": 2,
    "Alta": 3,
}


def _strongest_level(*levels: str) -> str:
    return max(
        levels,
        key=lambda value: _LEVEL_RANK.get(value, 0),
    )


def _structural_level(
    structural: SantanderPortfolioIntelligence,
) -> str:
    """Classify structural attention from existing Santander factual metrics."""

    high = False
    medium = False

    for concentration in structural.concentration_by_currency:
        top_1 = concentration.top_1_weight

        if top_1 is None:
            continue

        if top_1 >= 0.35:
            high = True
        elif top_1 > 0.20:
            medium = True

    coverage = structural.coverage

    if coverage.total_positions:
        economic_ratio = (
            coverage.positions_with_economic_class
            / coverage.total_positions
        )

        if economic_ratio < 0.80:
            high = True
        elif economic_ratio < 0.95:
            medium = True

    if structural.warnings:
        medium = True

    if high:
        return "Alta"

    if medium:
        return "Média"

    return "Baixa"


def _structural_attention(
    structural: SantanderPortfolioIntelligence,
) -> tuple[SantanderOperationalAttention, ...]:
    items: list[SantanderOperationalAttention] = []

    for concentration in structural.concentration_by_currency:
        top_1 = concentration.top_1_weight

        if top_1 is None:
            continue

        if top_1 >= 0.35:
            items.append(
                SantanderOperationalAttention(
                    source="STRUCTURAL",
                    level="Alta",
                    reason="concentration",
                )
            )
        elif top_1 > 0.20:
            items.append(
                SantanderOperationalAttention(
                    source="STRUCTURAL",
                    level="Média",
                    reason="concentration",
                )
            )

    coverage = structural.coverage

    if coverage.total_positions:
        economic_ratio = (
            coverage.positions_with_economic_class
            / coverage.total_positions
        )

        if economic_ratio < 0.80:
            items.append(
                SantanderOperationalAttention(
                    source="STRUCTURAL",
                    level="Alta",
                    reason="coverage",
                )
            )
        elif economic_ratio < 0.95:
            items.append(
                SantanderOperationalAttention(
                    source="STRUCTURAL",
                    level="Média",
                    reason="coverage",
                )
            )

    if structural.warnings:
        items.append(
            SantanderOperationalAttention(
                source="STRUCTURAL",
                level="Média",
                reason="data_quality",
            )
        )

    unique: dict[
        tuple[str, str, str, str | None],
        SantanderOperationalAttention,
    ] = {}

    for item in items:
        key = (
            item.source,
            item.level,
            item.reason,
            item.identifier,
        )
        unique.setdefault(key, item)

    return tuple(unique.values())


def _quantitative_attention(
    quantitative: SantanderQuantitativeIntelligence,
) -> tuple[SantanderOperationalAttention, ...]:
    items: list[SantanderOperationalAttention] = []

    for position in quantitative.attention_positions:
        for reason in position.attention_reasons:
            items.append(
                SantanderOperationalAttention(
                    source="QUANTITATIVE",
                    level=position.attention_level,
                    reason=reason,
                    identifier=position.identifier,
                    asset_label=position.asset_label,
                )
            )

    return tuple(items)


def _attention_sort_key(
    item: SantanderOperationalAttention,
) -> tuple:
    return (
        -_LEVEL_RANK.get(item.level, 0),
        0 if item.source == "QUANTITATIVE" else 1,
        item.identifier or "",
        item.reason,
    )


def _executive_reading(
    *,
    overall_level: str,
    structural_level: str,
    quantitative_level: str,
    quantitative: SantanderQuantitativeIntelligence,
) -> str:
    if (
        structural_level == "Baixa"
        and quantitative.analyzed_position_count == 0
    ):
        return (
            "A estrutura da carteira Santander não apresenta um ponto dominante "
            "de atenção, mas ainda não há histórico de mercado suficiente "
            "para completar a leitura quantitativa."
        )

    if overall_level == "Alta":
        if (
            structural_level == "Alta"
            and quantitative_level == "Alta"
        ):
            return (
                "A carteira Santander apresenta pontos relevantes tanto na estrutura "
                "quanto no comportamento histórico de mercado. "
                "Esses fatores merecem atenção prioritária."
            )

        if quantitative_level == "Alta":
            return (
                "A estrutura da carteira Santander não é o principal fator de atenção, "
                "mas o comportamento histórico de mercado de pelo menos uma posição "
                "merece atenção prioritária."
            )

        return (
            "A estrutura da carteira Santander apresenta um ponto relevante de atenção "
            "e merece acompanhamento prioritário."
        )

    if overall_level == "Média":
        return (
            "A carteira Santander apresenta alguns pontos de atenção estrutural ou "
            "quantitativa que merecem acompanhamento, sem um fator dominante "
            "de risco elevado neste momento."
        )

    return (
        "A leitura combinada da carteira Santander não apresenta, neste momento, "
        "um fator dominante de atenção estrutural ou quantitativa."
    )


def build_santander_operational_intelligence(
    structural: SantanderPortfolioIntelligence,
    quantitative: SantanderQuantitativeIntelligence,
) -> SantanderOperationalIntelligence:
    """Combine validated Santander structural and quantitative intelligence."""

    if structural.institution != "Santander":
        raise ValueError(
            "structural intelligence must belong to Santander"
        )

    if quantitative.institution != "Santander":
        raise ValueError(
            "quantitative intelligence must belong to Santander"
        )

    if structural.owner is not PortfolioOwner.JOLIKA:
        raise ValueError(
            "structural intelligence must belong to JOLIKA"
        )

    if quantitative.owner is not PortfolioOwner.JOLIKA:
        raise ValueError(
            "quantitative intelligence must belong to JOLIKA"
        )

    structural_level = _structural_level(
        structural
    )
    quantitative_level = quantitative.assessment.level

    overall_level = _strongest_level(
        structural_level,
        quantitative_level,
    )

    attention_items = tuple(
        sorted(
            (
                _structural_attention(structural)
                + _quantitative_attention(quantitative)
            ),
            key=_attention_sort_key,
        )
    )

    return SantanderOperationalIntelligence(
        institution="Santander",
        owner=PortfolioOwner.JOLIKA,
        structural_level=structural_level,
        quantitative_level=quantitative_level,
        overall_level=overall_level,
        attention_items=attention_items,
        analyzed_quantitative_positions=(
            quantitative.analyzed_position_count
        ),
        unavailable_quantitative_positions=(
            quantitative.unavailable_position_count
        ),
        executive_reading=_executive_reading(
            overall_level=overall_level,
            structural_level=structural_level,
            quantitative_level=quantitative_level,
            quantitative=quantitative,
        ),
    )
