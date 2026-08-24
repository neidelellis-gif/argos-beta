"""Operational intelligence for the consolidated JOLIKA portfolio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.jolika_portfolio_intelligence import (
    JolikaPortfolioIntelligence,
)
from backend.models import PortfolioOwner
from backend.santander_operational_intelligence import (
    SantanderOperationalIntelligence,
)
from backend.ubs_operational_intelligence import (
    UBSOperationalIntelligence,
)


_LEVEL_RANK = {
    "Baixa": 1,
    "Média": 2,
    "Alta": 3,
}


@dataclass(frozen=True)
class JolikaInstitutionAssessment:
    """Operational assessment inherited from one JOLIKA institution."""

    institution: str
    structural_level: str
    quantitative_level: str
    overall_level: str
    analyzed_quantitative_positions: int
    unavailable_quantitative_positions: int
    executive_reading: str


@dataclass(frozen=True)
class JolikaOperationalAttention:
    """One factual reason for attention in the consolidated JOLIKA portfolio."""

    source: str
    level: str
    reason: str
    institution: str | None = None
    identifier: str | None = None
    asset_label: str | None = None


@dataclass(frozen=True)
class JolikaOperationalIntelligence:
    """Combined consolidated and institution-level intelligence for JOLIKA."""

    owner: PortfolioOwner

    structural_level: str
    institutional_level: str
    overall_level: str

    institution_assessments: tuple[JolikaInstitutionAssessment, ...]
    attention_items: tuple[JolikaOperationalAttention, ...]

    analyzed_quantitative_positions: int
    unavailable_quantitative_positions: int

    executive_reading: str


def _strongest_level(*levels: str) -> str:
    if not levels:
        return "Baixa"

    return max(
        levels,
        key=lambda value: _LEVEL_RANK.get(value, 0),
    )


def _institution_name(
    operational: UBSOperationalIntelligence
    | SantanderOperationalIntelligence,
) -> str:
    return operational.institution


def _validate_institutional(
    operational: UBSOperationalIntelligence
    | SantanderOperationalIntelligence,
) -> None:
    if operational.owner is not PortfolioOwner.JOLIKA:
        raise ValueError(
            "institutional operational intelligence must belong to JOLIKA"
        )


def _institution_assessment(
    operational: UBSOperationalIntelligence
    | SantanderOperationalIntelligence,
) -> JolikaInstitutionAssessment:
    return JolikaInstitutionAssessment(
        institution=operational.institution,
        structural_level=operational.structural_level,
        quantitative_level=operational.quantitative_level,
        overall_level=operational.overall_level,
        analyzed_quantitative_positions=(
            operational.analyzed_quantitative_positions
        ),
        unavailable_quantitative_positions=(
            operational.unavailable_quantitative_positions
        ),
        executive_reading=operational.executive_reading,
    )


def _structural_attention(
    structural: JolikaPortfolioIntelligence,
) -> tuple[JolikaOperationalAttention, ...]:
    items: list[JolikaOperationalAttention] = []

    for reason in structural.priority.reasons:
        items.append(
            JolikaOperationalAttention(
                source="CONSOLIDATED_STRUCTURAL",
                level=structural.priority.level,
                reason=reason,
            )
        )

    return tuple(items)


def _institutional_attention(
    operational: UBSOperationalIntelligence
    | SantanderOperationalIntelligence,
) -> tuple[JolikaOperationalAttention, ...]:
    institution = _institution_name(operational)

    return tuple(
        JolikaOperationalAttention(
            source=item.source,
            level=item.level,
            reason=item.reason,
            institution=institution,
            identifier=item.identifier,
            asset_label=item.asset_label,
        )
        for item in operational.attention_items
    )


def _attention_sort_key(
    item: JolikaOperationalAttention,
) -> tuple:
    return (
        -_LEVEL_RANK.get(item.level, 0),
        0 if item.source == "QUANTITATIVE" else 1,
        item.institution or "",
        item.identifier or "",
        item.reason,
    )


def _deduplicate_attention(
    items: Iterable[JolikaOperationalAttention],
) -> tuple[JolikaOperationalAttention, ...]:
    unique: dict[
        tuple[
            str,
            str,
            str,
            str | None,
            str | None,
            str | None,
        ],
        JolikaOperationalAttention,
    ] = {}

    for item in items:
        key = (
            item.source,
            item.level,
            item.reason,
            item.institution,
            item.identifier,
            item.asset_label,
        )
        unique.setdefault(key, item)

    return tuple(
        sorted(
            unique.values(),
            key=_attention_sort_key,
        )
    )


def _executive_reading(
    *,
    structural_level: str,
    institutional_level: str,
    overall_level: str,
    institution_count: int,
    analyzed_quantitative_positions: int,
) -> str:
    if institution_count == 0:
        return (
            "Ainda não há instituições com inteligência operacional "
            "disponível para completar a leitura consolidada da Jolika."
        )

    if analyzed_quantitative_positions == 0:
        if structural_level == "Alta":
            return (
                "A carteira consolidada da Jolika apresenta um ponto estrutural "
                "relevante de atenção, mas ainda não há histórico de mercado "
                "suficiente para completar a leitura quantitativa das instituições."
            )

        if structural_level == "Média":
            return (
                "A carteira consolidada da Jolika apresenta alguns pontos "
                "estruturais que merecem acompanhamento, mas ainda não há "
                "histórico de mercado suficiente para completar a leitura "
                "quantitativa das instituições."
            )

        return (
            "A estrutura consolidada da carteira Jolika não apresenta um ponto "
            "dominante de atenção, mas ainda não há histórico de mercado "
            "suficiente para completar a leitura quantitativa das instituições."
        )

    if overall_level == "Alta":
        if (
            structural_level == "Alta"
            and institutional_level == "Alta"
        ):
            return (
                "A carteira consolidada da Jolika apresenta pontos relevantes "
                "tanto na estrutura consolidada quanto nas leituras das "
                "instituições. Esses fatores merecem atenção prioritária."
            )

        if structural_level == "Alta":
            return (
                "A estrutura consolidada da carteira Jolika apresenta um ponto "
                "relevante de atenção e merece acompanhamento prioritário."
            )

        return (
            "A estrutura consolidada não é o principal fator de atenção, "
            "mas pelo menos uma das instituições da Jolika apresenta uma "
            "leitura operacional que merece atenção prioritária."
        )

    if overall_level == "Média":
        return (
            "A carteira consolidada da Jolika apresenta alguns pontos de atenção "
            "estrutural ou institucional que merecem acompanhamento, sem um "
            "fator dominante de risco elevado neste momento."
        )

    return (
        "A leitura consolidada da carteira Jolika não apresenta, neste momento, "
        "um fator dominante de atenção estrutural ou institucional."
    )


def build_jolika_operational_intelligence(
    structural: JolikaPortfolioIntelligence,
    institutionals: Iterable[
        UBSOperationalIntelligence
        | SantanderOperationalIntelligence
    ],
) -> JolikaOperationalIntelligence:
    """Combine consolidated structure with validated institution intelligence."""

    if structural.owner is not PortfolioOwner.JOLIKA:
        raise ValueError(
            "structural intelligence must belong to JOLIKA"
        )

    institutional_items = tuple(institutionals)

    for operational in institutional_items:
        if not isinstance(
            operational,
            (
                UBSOperationalIntelligence,
                SantanderOperationalIntelligence,
            ),
        ):
            raise TypeError(
                "institutionals accepts only supported operational "
                "intelligence instances"
            )

        _validate_institutional(operational)

    ordered_institutionals = tuple(
        sorted(
            institutional_items,
            key=lambda item: item.institution.casefold(),
        )
    )

    assessments = tuple(
        _institution_assessment(item)
        for item in ordered_institutionals
    )

    institutional_levels = tuple(
        item.overall_level
        for item in ordered_institutionals
    )

    institutional_level = _strongest_level(
        *institutional_levels
    )

    structural_level = structural.priority.level

    overall_level = _strongest_level(
        structural_level,
        institutional_level,
    )

    attention: list[JolikaOperationalAttention] = list(
        _structural_attention(structural)
    )

    for operational in ordered_institutionals:
        attention.extend(
            _institutional_attention(operational)
        )

    analyzed = sum(
        item.analyzed_quantitative_positions
        for item in ordered_institutionals
    )

    unavailable = sum(
        item.unavailable_quantitative_positions
        for item in ordered_institutionals
    )

    return JolikaOperationalIntelligence(
        owner=PortfolioOwner.JOLIKA,
        structural_level=structural_level,
        institutional_level=institutional_level,
        overall_level=overall_level,
        institution_assessments=assessments,
        attention_items=_deduplicate_attention(attention),
        analyzed_quantitative_positions=analyzed,
        unavailable_quantitative_positions=unavailable,
        executive_reading=_executive_reading(
            structural_level=structural_level,
            institutional_level=institutional_level,
            overall_level=overall_level,
            institution_count=len(ordered_institutionals),
            analyzed_quantitative_positions=analyzed,
        ),
    )
