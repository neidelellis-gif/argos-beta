"""Build the five-stage ARGOS report for the consolidated JOLIKA portfolio."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from backend.institution_patrimonial_report import _asset_attention_lines
from backend.jolika_market_context_analysis import build_market_context_stage
from backend.jolika_master_assumptions_analysis import build_master_assumptions_stage
from backend.patrimonial_analysis_method import (
    PatrimonialAnalysisItem,
    PatrimonialAnalysisReport,
    PatrimonialAnalysisStage,
    build_patrimonial_analysis_report,
)


def _pct(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.1f}%"


def _class_label(value: Any) -> str:
    return getattr(value, "value", str(value))


def _composition_items(structural: Any) -> tuple[PatrimonialAnalysisItem, ...]:
    items: list[PatrimonialAnalysisItem] = []
    for currency, allocation in structural.economic_allocation_by_currency:
        total = sum((amount for _, amount in allocation), Decimal(0))
        if total <= 0:
            continue
        reading = " · ".join(
            f"{_class_label(asset_class)} {_pct(amount / total)}"
            for asset_class, amount in sorted(allocation, key=lambda pair: pair[1], reverse=True)
        )
        items.append(PatrimonialAnalysisItem(
            title=f"Onde o patrimônio está — {currency}",
            reading=reading,
            evidence=("consolidação econômica das instituições carregadas",),
            confidence="Alta",
        ))

    for concentration in structural.concentration_by_currency:
        items.append(PatrimonialAnalysisItem(
            title=f"Quanto depende das maiores posições — {concentration.currency}",
            reading=(
                f"Maior posição {_pct(concentration.top_1_weight)} · "
                f"Top 3 {_pct(concentration.top_3_weight)} · "
                f"Top 5 {_pct(concentration.top_5_weight)}."
            ),
            evidence=("exposições consolidadas por ativo",),
            confidence="Alta",
        ))

    duplicate_count = sum(1 for item in structural.duplicate_exposures if item.across_institutions)
    items.append(PatrimonialAnalysisItem(
        title="Exposições repetidas entre instituições",
        reading=(
            f"{duplicate_count} exposição(ões) identificada(s) entre instituições."
            if duplicate_count
            else "Nenhuma exposição repetida material foi identificada entre as instituições."
        ),
        evidence=("identificadores consolidados UBS + Santander",),
        confidence="Alta",
    ))
    return tuple(items)


def _institution_items(institutional: Iterable[Any]) -> tuple[PatrimonialAnalysisItem, ...]:
    return tuple(
        PatrimonialAnalysisItem(
            title=item.structural.institution,
            reading=item.operational.executive_reading,
            evidence=("diagnóstico institucional concluído",),
            confidence="Média",
        )
        for item in institutional
    )


def _final_items(structural: Any, operational: Any) -> tuple[PatrimonialAnalysisItem, ...]:
    strengths: list[str] = []
    attention: list[str] = list(_asset_attention_lines(operational))

    concentrations = tuple(getattr(structural, "concentration_by_currency", ()) or ())
    if concentrations:
        strongest = max(
            concentrations,
            key=lambda item: float(getattr(item, "top_1_weight", 0) or 0),
        )
        currency = getattr(strongest, "currency", "moeda identificada")
        top_1 = float(getattr(strongest, "top_1_weight", 0) or 0)
        top_5 = float(getattr(strongest, "top_5_weight", 0) or 0)

        if top_1 < 0.15:
            strengths.append(
                f"Nenhuma posição domina o conjunto: a maior representa {top_1 * 100:.1f}% em {currency}."
            )
        if top_5 and top_5 < 0.55:
            strengths.append(
                f"As 5 maiores posições somam {top_5 * 100:.1f}% em {currency}; "
                "o restante está distribuído entre os demais investimentos."
            )

    allocations = tuple(getattr(structural, "economic_allocation_by_currency", ()) or ())
    if len(allocations) == 1:
        currency, allocation = allocations[0]
        positive = [
            (asset_class, amount)
            for asset_class, amount in allocation
            if amount is not None and amount > 0
        ]
        total = sum((amount for _, amount in positive), Decimal(0))
        if total > 0 and len(positive) >= 4:
            top_class, top_amount = max(positive, key=lambda pair: pair[1])
            strengths.append(
                f"O patrimônio consolidado está distribuído entre {len(positive)} classes; "
                f"a maior é {_class_label(top_class)}, com {_pct(top_amount / total)} em {currency}."
            )

    if (
        not any(item.across_institutions for item in structural.duplicate_exposures)
        and len(strengths) < 3
    ):
        strengths.append("Não há exposição repetida material identificada entre UBS e Santander.")

    if operational.structural_level == "Alta" and len(attention) < 3:
        attention.append(
            "Estrutura consolidada — concentração ou cobertura de dados também merece avaliação."
        )
    if operational.unavailable_quantitative_positions and len(attention) < 3:
        attention.append(
            "Cobertura — parte das posições ainda não possui histórico suficiente para uma leitura quantitativa completa."
        )

    strengths = strengths[:3]
    attention = attention[:3]
    primary_asset = ""
    if attention:
        primary_asset = attention[0].split(" — ", 1)[0].rstrip(".:")

    def make(title: str, values: list[str], fallback: str) -> PatrimonialAnalysisItem:
        return PatrimonialAnalysisItem(
            title=title,
            reading=" • ".join(values) if values else fallback,
            evidence=("carteira consolidada UBS + Santander",),
            confidence="Média",
        )

    return (
        make(
            "O que está bem",
            strengths,
            "Nenhum ponto positivo adicional foi confirmado com evidência suficiente.",
        ),
        make(
            "O que merece atenção",
            attention,
            "Nenhum problema relevante foi confirmado com os dados atuais.",
        ),
        PatrimonialAnalysisItem(
            title="Encaminhamento",
            reading=(
                f"O principal ponto de atenção hoje é {primary_asset}. "
                "Sugerimos conversar com seu gerente de banco ou Banker para avaliar as providências adequadas "
                "caso esse comportamento persista ou se intensifique."
                if primary_asset
                else "Nada relevante exige providência neste momento."
            ),
            evidence=("carteira consolidada UBS + Santander",),
            confidence="Média",
        ),
    )

def build_jolika_patrimonial_report(
    structural: Any,
    operational: Any,
    institutional: Iterable[Any],
    *,
    positions: Iterable[Any] = (),
    facts: Iterable[Any] = (),
) -> PatrimonialAnalysisReport:
    """Recalculate and interpret the consolidated universe; never concatenate reports."""

    institutional = tuple(institutional)
    diagnosis = PatrimonialAnalysisStage(
        key="diagnosis",
        title="Diagnóstico da carteira",
        summary=operational.executive_reading,
        items=_institution_items(institutional),
    )
    composition = PatrimonialAnalysisStage(
        key="composition",
        title="Análise da composição",
        summary=(
            f"{structural.consolidated_asset_count} ativos econômicos consolidados a partir de "
            f"{len(structural.institutions)} instituição(ões), com concentração e duplicidades recalculadas no conjunto."
        ),
        items=_composition_items(structural),
    )
    master_assumptions = build_master_assumptions_stage(
        structural,
        operational=operational,
    )
    market_context = build_market_context_stage(positions, facts)
    final_diagnosis = PatrimonialAnalysisStage(
        key="final_diagnosis",
        title="Diagnóstico final",
        summary="O que está bem, o que merece atenção e o encaminhamento quando houver um problema confirmado.",
        items=_final_items(structural, operational),
    )
    return build_patrimonial_analysis_report(
        universe="JOLIKA",
        scope="consolidated",
        diagnosis=diagnosis,
        composition=composition,
        master_assumptions=master_assumptions,
        market_context=market_context,
        final_diagnosis=final_diagnosis,
    )
