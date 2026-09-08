"""Build the five-stage ARGOS report for the consolidated JOLIKA portfolio."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

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
            title=f"Classes de ativos — {currency}",
            reading=reading,
            evidence=("consolidação econômica das instituições carregadas",),
            confidence="Alta",
        ))

    for concentration in structural.concentration_by_currency:
        items.append(PatrimonialAnalysisItem(
            title=f"Concentração consolidada — {concentration.currency}",
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
    highlights: list[str] = []
    evolution: list[str] = []

    coverage = structural.coverage
    if coverage.consolidated_asset_count and coverage.assets_with_economic_class == coverage.consolidated_asset_count:
        strengths.append("Todos os ativos consolidados possuem classificação econômica.")
    if operational.structural_level == "Baixa":
        strengths.append("A estrutura consolidada não apresenta alerta dominante nas métricas atuais.")
    if not any(item.across_institutions for item in structural.duplicate_exposures):
        strengths.append("Não há exposição repetida material identificada entre UBS e Santander.")

    highlights.append(
        f"{structural.consolidated_asset_count} ativos consolidados em {len(structural.institutions)} instituição(ões)."
    )
    if operational.analyzed_quantitative_positions:
        highlights.append(
            f"{operational.analyzed_quantitative_positions} posições institucionais possuem leitura quantitativa histórica."
        )

    if operational.overall_level == "Alta":
        evolution.append("A leitura consolidada contém fatores de atenção prioritária que exigem aprofundamento.")
    elif operational.overall_level == "Média":
        evolution.append("A leitura consolidada contém pontos que merecem acompanhamento.")
    if operational.unavailable_quantitative_positions:
        evolution.append(
            f"{operational.unavailable_quantitative_positions} posições institucionais ainda não possuem cobertura quantitativa suficiente."
        )

    def make(title: str, values: list[str], fallback: str) -> PatrimonialAnalysisItem:
        return PatrimonialAnalysisItem(
            title=title,
            reading=" ".join(values) if values else fallback,
            evidence=("inteligência consolidada do ARGOS",),
            confidence="Média",
        )

    return (
        make("Pontos fortes", strengths, "Nenhum ponto forte adicional foi confirmado com evidência suficiente."),
        make("Destaques", highlights, "Nenhum destaque adicional foi confirmado com evidência suficiente."),
        make("Pontos de evolução", evolution, "Nenhum ponto de evolução material foi confirmado com os dados atuais."),
    )


def build_jolika_patrimonial_report(
    structural: Any,
    operational: Any,
    institutional: Iterable[Any],
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
    master_assumptions = unavailable_stage(
        "master_assumptions",
        "Aderência às Premissas Mestres da JOLIKA",
        "A fonte canônica das Premissas Mestres ainda não está formalizada no backend; nenhuma aderência consolidada é inferida.",
    )
    market_context = unavailable_stage(
        "market_context",
        "Carteira × ambiente de mercado",
        "O contexto editorial de mercado e newsletters ainda não está conectado a este relatório consolidado; nenhuma leitura externa é inventada.",
    )
    final_diagnosis = PatrimonialAnalysisStage(
        key="final_diagnosis",
        title="Diagnóstico final",
        summary="Síntese da carteira econômica consolidada, separada dos diagnósticos individuais.",
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
