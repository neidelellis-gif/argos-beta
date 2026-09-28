"""Build the five-stage ARGOS report for the consolidated JOLIKA portfolio."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from backend.jolika_master_assumptions_analysis import build_master_assumptions_stage
from backend.jolika_market_context_analysis import build_market_context_stage
from backend.patrimonial_analysis_method import (
    PatrimonialAnalysisItem,
    PatrimonialAnalysisReport,
    PatrimonialAnalysisStage,
    build_patrimonial_analysis_report,
    unavailable_stage,
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
        total = sum((amount for _, amount in allocation), Decimal("0"))
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
                f"Maior exposição {_pct(concentration.top_1_weight)} · "
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
    attention: list[str] = []

    coverage = structural.coverage
    if coverage.consolidated_asset_count and coverage.assets_with_economic_class == coverage.consolidated_asset_count:
        strengths.append("Todos os investimentos consolidados estão identificados e classificados.")
    if operational.structural_level == "Baixa":
        strengths.append("A estrutura consolidada não mostra um problema dominante neste momento.")
    if not any(item.across_institutions for item in structural.duplicate_exposures):
        strengths.append("Não há exposição repetida material identificada entre UBS e Santander.")

    if operational.overall_level == "Alta":
        attention.append("A carteira consolidada tem pontos de atenção prioritários que precisam ser avaliados.")
    elif operational.overall_level == "Média":
        attention.append("A carteira consolidada tem pontos que merecem acompanhamento.")
    if operational.unavailable_quantitative_positions:
        attention.append(
            "Parte das posições ainda não tem histórico suficiente; isso limita algumas conclusões."
        )

    has_attention = bool(attention)

    def make(title: str, values: list[str], fallback: str) -> PatrimonialAnalysisItem:
        return PatrimonialAnalysisItem(
            title=title,
            reading=" ".join(values) if values else fallback,
            evidence=("carteira consolidada",),
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
                "Há pontos que merecem avaliação. Sugerimos conversar com seu gerente de banco ou Banker "
                "para avaliar as providências adequadas."
                if has_attention
                else "Nada relevante exige providência neste momento."
            ),
            evidence=("carteira consolidada",),
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
