"""Build the shared five-stage ARGOS report for one JOLIKA institution."""

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
                title=f"Onde o patrimônio está — {currency}",
                reading=reading,
                evidence=("classificação econômica da carteira importada",),
                confidence="Alta",
            )
        )

    for concentration in structural.concentration_by_currency:
        items.append(
            PatrimonialAnalysisItem(
                title=f"Quanto depende das maiores posições — {concentration.currency}",
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
                title="Quanto os investimentos oscilaram",
                reading=(
                    f"Maior oscilação estimada para um ano: {max(volatilities) * 100:.1f}%, "
                    "entre os ativos com histórico suficiente."
                ),
                evidence=(
                    f"histórico de mercado de até {quantitative.lookback_days} dias",
                ),
                confidence="Média",
            )
        )
    if drawdowns:
        items.append(
            PatrimonialAnalysisItem(
                title="Maior queda no período",
                reading=(
                    f"Maior queda do ponto mais alto ao mais baixo: {max(drawdowns) * 100:.1f}%, "
                    "entre os ativos com histórico suficiente."
                ),
                evidence=(
                    f"histórico de mercado de até {quantitative.lookback_days} dias",
                ),
                confidence="Média",
            )
        )
    return tuple(items)


_ATTENTION_REASON_TEXT = {
    "high_volatility": "oscilações elevadas",
    "elevated_volatility": "oscilações elevadas",
    "deep_drawdown": "uma queda relevante no período",
    "relevant_drawdown": "uma queda relevante no período",
    "high_var": "dias de queda mais fortes no histórico recente",
    "elevated_var": "dias de queda mais fortes no histórico recente",
    "high_cvar": "quedas mais intensas nos piores dias do histórico recente",
    "elevated_cvar": "quedas mais intensas nos piores dias do histórico recente",
}


def _asset_attention_lines(operational: Any) -> tuple[str, ...]:
    grouped: dict[str, list[str]] = {}

    for attention in tuple(getattr(operational, "attention_items", ()) or ()):
        if getattr(attention, "source", None) != "QUANTITATIVE":
            continue

        label = (getattr(attention, "asset_label", None) or "").strip()
        identifier = (getattr(attention, "identifier", None) or "").strip()
        if not label and not identifier:
            continue

        if label and identifier and identifier.casefold() not in label.casefold():
            asset = f"{label} ({identifier})"
        else:
            asset = label or identifier

        reason = _ATTENTION_REASON_TEXT.get(
            getattr(attention, "reason", ""),
            "um comportamento de mercado que merece atenção",
        )
        grouped.setdefault(asset, [])
        if reason not in grouped[asset]:
            grouped[asset].append(reason)

    lines: list[str] = []
    for asset, reasons in grouped.items():
        if len(reasons) == 1:
            reason_text = reasons[0]
        else:
            reason_text = ", ".join(reasons[:-1]) + " e " + reasons[-1]
        lines.append(f"{asset}: {reason_text}.")
    return tuple(lines)


def _final_items(structural: Any, quantitative: Any, operational: Any) -> tuple[PatrimonialAnalysisItem, ...]:
    strengths: list[str] = []
    attention: list[str] = []

    coverage = structural.coverage
    if coverage.total_positions and coverage.positions_with_economic_class == coverage.total_positions:
        strengths.append("Todos os investimentos estão identificados e classificados.")

    if operational.structural_level == "Baixa":
        strengths.append("A estrutura da carteira não mostra um problema dominante neste momento.")
    elif operational.structural_level == "Alta":
        attention.append("Há concentração ou cobertura de dados que merece avaliação.")

    asset_attention = _asset_attention_lines(operational)

    if operational.quantitative_level == "Baixa":
        strengths.append("Os movimentos recentes não mostram um ponto de atenção dominante.")
    elif asset_attention:
        attention.extend(asset_attention)

    if structural.warnings:
        attention.append("Há dados da carteira que precisam ser conferidos antes de qualquer providência.")

    has_attention = bool(attention)

    def item(title: str, values: list[str], fallback: str) -> PatrimonialAnalysisItem:
        return PatrimonialAnalysisItem(
            title=title,
            reading=" ".join(values) if values else fallback,
            evidence=("carteira atual", "histórico de mercado disponível"),
            confidence="Média",
        )

    return (
        item(
            "O que está bem",
            strengths,
            "Nenhum ponto positivo adicional foi confirmado com evidência suficiente.",
        ),
        item(
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
            evidence=("carteira atual", "histórico de mercado disponível"),
            confidence="Média",
        ),
    )

def build_institution_patrimonial_report(
    structural: Any,
    quantitative: Any,
    operational: Any,
    *,
    positions: Iterable[Any] = (),
    facts: Iterable[Any] = (),
) -> PatrimonialAnalysisReport:
    """Apply the official five-stage method to UBS or Santander in isolation."""

    institution = structural.institution
    analyzed_count = quantitative.analyzed_position_count
    unavailable_count = quantitative.unavailable_position_count
    total_quantitative = analyzed_count + unavailable_count
    coverage_note = (
        f"A análise considera as {structural.position_count} posições da carteira. "
        "Histórico incompleto limita indicadores, mas não exclui investimentos."
    )

    diagnosis = PatrimonialAnalysisStage(
        key="diagnosis",
        title="Diagnóstico da carteira",
        summary=operational.executive_reading,
        items=(
            PatrimonialAnalysisItem(
                title="Leitura de hoje",
                reading=coverage_note,
                evidence=(
                    "carteira atual",
                    "histórico de mercado disponível",
                ),
                confidence="Alta" if unavailable_count == 0 and total_quantitative else "Parcial",
            ),
        ),
    )

    composition_items = _composition_items(structural) + _quantitative_items(quantitative)
    composition = PatrimonialAnalysisStage(
        key="composition",
        title="Análise da composição",
        summary=(
            f"{structural.position_count} posições em "
            f"{', '.join(structural.currencies) or 'moeda não identificada'}: distribuição e concentração."
        ),
        items=composition_items,
        status="available" if composition_items else "limited",
    )

    master_assumptions = build_master_assumptions_stage(
        structural,
        quantitative=quantitative,
        operational=operational,
    )

    market_context = build_market_context_stage(positions, facts)

    final_diagnosis = PatrimonialAnalysisStage(
        key="final_diagnosis",
        title="Diagnóstico final",
        summary=(
            "O que está bem, o que merece atenção e o encaminhamento quando houver um problema confirmado."
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
