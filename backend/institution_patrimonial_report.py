"""Build the shared five-stage ARGOS report for one JOLIKA institution."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.patrimonial_analysis_method import (
    PatrimonialAnalysisItem,
    PatrimonialAnalysisReport,
    PatrimonialAnalysisStage,
    build_patrimonial_analysis_report,
    unavailable_stage,
)


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _economic_class_label(value: Any) -> str:
    return getattr(value, "value", str(value))


def _composition_items(structural: Any) -> tuple[PatrimonialAnalysisItem, ...]:
    items: list[PatrimonialAnalysisItem] = []

    for currency, allocation in structural.economic_allocation_by_currency:
        total = sum((amount for _, amount in allocation), Decimal("0"))
        if total <= 0:
            continue
        reading = " · ".join(
            f"{_economic_class_label(asset_class)} {_pct(amount / total)}"
            for asset_class, amount in sorted(
                allocation,
                key=lambda pair: pair[1],
                reverse=True,
            )
        )
        items.append(
            PatrimonialAnalysisItem(
                title=f"Classes de ativos — {currency}",
                reading=reading,
                evidence=("classificação econômica da carteira importada",),
                confidence="Alta",
            )
        )

    for concentration in structural.concentration_by_currency:
        items.append(
            PatrimonialAnalysisItem(
                title=f"Concentração — {concentration.currency}",
                reading=(
                    f"Maior posição {_pct(concentration.top_1_weight)} · "
                    f"Top 3 {_pct(concentration.top_3_weight)} · "
                    f"Top 5 {_pct(concentration.top_5_weight)}."
                ),
                evidence=("valores de mercado importados",),
                confidence="Alta",
            )
        )

    return tuple(items)


def _quantitative_items(quantitative: Any) -> tuple[PatrimonialAnalysisItem, ...]:
    analyzed = tuple(
        position
        for position in quantitative.positions
        if getattr(position, "status", None) == "available"
    )
    if not analyzed:
        return ()

    volatilities = [
        position.annualized_volatility
        for position in analyzed
        if position.annualized_volatility is not None
    ]
    drawdowns = [
        abs(position.maximum_drawdown)
        for position in analyzed
        if position.maximum_drawdown is not None
    ]

    items: list[PatrimonialAnalysisItem] = []
    if volatilities:
        items.append(
            PatrimonialAnalysisItem(
                title="Volatilidade histórica",
                reading=(
                    f"Maior volatilidade anualizada entre os ativos analisados: "
                    f"{max(volatilities) * 100:.1f}%."
                ),
                evidence=(
                    f"histórico de mercado de até {quantitative.lookback_days} dias",
                    f"{quantitative.analyzed_position_count} posições analisadas",
                ),
                confidence="Média",
            )
        )
    if drawdowns:
        items.append(
            PatrimonialAnalysisItem(
                title="Drawdown histórico",
                reading=(
                    f"Maior drawdown entre os ativos analisados: "
                    f"{max(drawdowns) * 100:.1f}%."
                ),
                evidence=(
                    f"histórico de mercado de até {quantitative.lookback_days} dias",
                ),
                confidence="Média",
            )
        )
    return tuple(items)


def _final_items(structural: Any, quantitative: Any, operational: Any) -> tuple[PatrimonialAnalysisItem, ...]:
    strengths: list[str] = []
    highlights: list[str] = []
    evolution: list[str] = []

    coverage = structural.coverage
    if coverage.total_positions and coverage.positions_with_economic_class == coverage.total_positions:
        strengths.append("100% das posições possuem classificação econômica.")

    if operational.structural_level == "Baixa":
        strengths.append("Não há alerta estrutural dominante nas métricas atuais.")
    elif operational.structural_level == "Alta":
        evolution.append("A estrutura da carteira exige aprofundamento por concentração ou qualidade de cobertura.")

    if operational.quantitative_level == "Baixa":
        strengths.append("O motor quantitativo não identificou alerta dominante entre os ativos com histórico disponível.")
    elif operational.quantitative_level == "Alta":
        evolution.append("Há ativos com risco histórico elevado que merecem aprofundamento individual.")

    if quantitative.analyzed_position_count:
        highlights.append(
            f"{quantitative.analyzed_position_count} posições possuem leitura quantitativa com histórico de mercado."
        )
    if quantitative.unavailable_position_count:
        evolution.append(
            f"{quantitative.unavailable_position_count} posições ainda não possuem cobertura quantitativa suficiente."
        )

    if structural.warnings:
        evolution.append("Há alertas de qualidade de dados que devem permanecer visíveis na análise.")

    def item(title: str, values: list[str], fallback: str) -> PatrimonialAnalysisItem:
        return PatrimonialAnalysisItem(
            title=title,
            reading=" ".join(values) if values else fallback,
            evidence=("inteligência estrutural e quantitativa do ARGOS",),
            confidence="Média",
        )

    return (
        item("Pontos fortes", strengths, "Nenhum ponto forte adicional foi confirmado com evidência suficiente."),
        item("Destaques", highlights, "Nenhum destaque adicional foi confirmado com evidência suficiente."),
        item("Pontos de evolução", evolution, "Nenhum ponto de evolução material foi confirmado com os dados atuais."),
    )


def build_institution_patrimonial_report(
    structural: Any,
    quantitative: Any,
    operational: Any,
) -> PatrimonialAnalysisReport:
    """Apply the official five-stage method to UBS or Santander in isolation."""

    institution = structural.institution

    diagnosis = PatrimonialAnalysisStage(
        key="diagnosis",
        title="Diagnóstico da carteira",
        summary=operational.executive_reading,
        items=(
            PatrimonialAnalysisItem(
                title="Leitura executiva",
                reading=operational.executive_reading,
                evidence=(
                    "carteira importada",
                    "métricas estruturais",
                    "métricas quantitativas históricas",
                ),
                confidence=(
                    "Média"
                    if quantitative.analyzed_position_count
                    else "Baixa"
                ),
            ),
        ),
    )

    composition_items = _composition_items(structural) + _quantitative_items(quantitative)
    composition = PatrimonialAnalysisStage(
        key="composition",
        title="Análise da composição",
        summary=(
            f"{structural.position_count} posições analisadas em "
            f"{', '.join(structural.currencies) or 'moeda não identificada'}, "
            "com leitura por classes, concentração e risco histórico quando disponível."
        ),
        items=composition_items,
        status="available" if composition_items else "limited",
    )

    master_assumptions = unavailable_stage(
        "master_assumptions",
        "Aderência às Premissas Mestres da JOLIKA",
        "As Premissas Mestres ainda não estão disponíveis para este serviço de backend; nenhuma aderência é inferida sem essa base.",
    )

    market_context = unavailable_stage(
        "market_context",
        "Carteira × ambiente de mercado",
        "O contexto editorial de mercado e newsletters ainda não está conectado a este relatório institucional; o ARGOS mantém esta etapa explícita sem inventar uma leitura externa.",
    )

    final_diagnosis = PatrimonialAnalysisStage(
        key="final_diagnosis",
        title="Diagnóstico final",
        summary=(
            "Síntese baseada somente nas evidências estruturais e quantitativas disponíveis nesta instituição."
        ),
        items=_final_items(structural, quantitative, operational),
    )

    return build_patrimonial_analysis_report(
        universe=institution,
        scope="institution",
        diagnosis=diagnosis,
        composition=composition,
        master_assumptions=master_assumptions,
        market_context=market_context,
        final_diagnosis=final_diagnosis,
    )
