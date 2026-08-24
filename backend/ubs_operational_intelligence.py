"""Operational intelligence for the JOLIKA portfolio held at UBS."""

from __future__ import annotations

from dataclasses import dataclass

from backend.models import PortfolioOwner
from backend.ubs_portfolio_intelligence import (
    UBSPortfolioIntelligence,
)
from backend.ubs_quantitative_intelligence import (
    UBSQuantitativeIntelligence,
)


@dataclass(frozen=True)
class UBSOperationalAttention:
    """One factual reason for executive attention."""

    source: str
    level: str
    reason: str
    identifier: str | None = None
    asset_label: str | None = None


@dataclass(frozen=True)
class UBSOperationalIntelligence:
    """Combined structural and quantitative reading for UBS/JOLIKA."""

    institution: str
    owner: PortfolioOwner

    structural_level: str
    quantitative_level: str
    overall_level: str

    attention_items: tuple[UBSOperationalAttention, ...]

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
    structural: UBSPortfolioIntelligence,
) -> str:
    """Classify structural attention from existing UBS factual metrics."""

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
    structural: UBSPortfolioIntelligence,
) -> tuple[UBSOperationalAttention, ...]:
    items: list[UBSOperationalAttention] = []

    for concentration in structural.concentration_by_currency:
        top_1 = concentration.top_1_weight

        if top_1 is None:
            continue

        if top_1 >= 0.35:
            items.append(
                UBSOperationalAttention(
                    source="STRUCTURAL",
                    level="Alta",
                    reason="concentration",
                )
            )
        elif top_1 > 0.20:
            items.append(
                UBSOperationalAttention(
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
                UBSOperationalAttention(
                    source="STRUCTURAL",
                    level="Alta",
                    reason="coverage",
                )
            )
        elif economic_ratio < 0.95:
            items.append(
                UBSOperationalAttention(
                    source="STRUCTURAL",
                    level="Média",
                    reason="coverage",
                )
            )

    if structural.warnings:
        items.append(
            UBSOperationalAttention(
                source="STRUCTURAL",
                level="Média",
                reason="data_quality",
            )
        )

    unique: dict[
        tuple[str, str, str, str | None],
        UBSOperationalAttention,
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
    quantitative: UBSQuantitativeIntelligence,
) -> tuple[UBSOperationalAttention, ...]:
    items: list[UBSOperationalAttention] = []

    for position in quantitative.attention_positions:
        for reason in position.attention_reasons:
            items.append(
                UBSOperationalAttention(
                    source="QUANTITATIVE",
                    level=position.attention_level,
                    reason=reason,
                    identifier=position.identifier,
                    asset_label=position.asset_label,
                )
            )

    return tuple(items)


def _attention_sort_key(
    item: UBSOperationalAttention,
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
    quantitative: UBSQuantitativeIntelligence,
) -> str:
    if (
        structural_level == "Baixa"
        and quantitative.analyzed_position_count == 0
    ):
        return (
            "A estrutura da carteira UBS não apresenta um ponto dominante "
            "de atenção, mas ainda não há histórico de mercado suficiente "
            "para completar a leitura quantitativa."
        )

    if overall_level == "Alta":
        if (
            structural_level == "Alta"
            and quantitative_level == "Alta"
        ):
            return (
                "A carteira UBS apresenta pontos relevantes tanto na estrutura "
                "quanto no comportamento histórico de mercado. "
                "Esses fatores merecem atenção prioritária."
            )

        if quantitative_level == "Alta":
            return (
                "A estrutura da carteira UBS não é o principal fator de atenção, "
                "mas o comportamento histórico de mercado de pelo menos uma posição "
                "merece atenção prioritária."
            )

        return (
            "A estrutura da carteira UBS apresenta um ponto relevante de atenção "
            "e merece acompanhamento prioritário."
        )

    if overall_level == "Média":
        return (
            "A carteira UBS apresenta alguns pontos de atenção estrutural ou "
            "quantitativa que merecem acompanhamento, sem um fator dominante "
            "de risco elevado neste momento."
        )

    return (
        "A leitura combinada da carteira UBS não apresenta, neste momento, "
        "um fator dominante de atenção estrutural ou quantitativa."
    )


def build_ubs_operational_intelligence(
    structural: UBSPortfolioIntelligence,
    quantitative: UBSQuantitativeIntelligence,
) -> UBSOperationalIntelligence:
    """Combine validated UBS structural and quantitative intelligence."""

    if structural.institution != "UBS":
        raise ValueError(
            "structural intelligence must belong to UBS"
        )

    if quantitative.institution != "UBS":
        raise ValueError(
            "quantitative intelligence must belong to UBS"
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

    return UBSOperationalIntelligence(
        institution="UBS",
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
