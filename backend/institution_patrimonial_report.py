"""Build the shared five-stage ARGOS report for one JOLIKA institution."""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from backend.jolika_market_context_analysis import build_market_context_stage
from backend.jolika_master_assumptions_analysis import build_master_assumptions_stage
from backend.patrimonial_analysis_method import (
    PatrimonialAnalysisItem,
    PatrimonialAnalysisReport,
    PatrimonialAnalysisStage,
    build_patrimonial_analysis_report,
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
        total = sum((amount for _, amount in allocation), Decimal(0))
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


def _display_asset_label(label: str, identifier: str) -> str:
    display = (label or identifier or "").strip()
    if not display:
        return ""

    if label:
        cleaned = label.strip()
        suffixes = re.compile(
            r"\s+(CORPORATION|CORP\.?|INC\.?|INCORPORATED|PLC|LTD\.?|LIMITED|COMPANY|CO\.?|ETF)$",
            re.IGNORECASE,
        )
        while True:
            shortened = suffixes.sub("", cleaned).strip()
            if shortened == cleaned:
                break
            cleaned = shortened

        if cleaned.isupper():
            if " " not in cleaned and len(cleaned) <= 6:
                display = cleaned
            else:
                words = []
                for word in cleaned.split():
                    upper = word.upper()
                    if upper in {"GE", "IBM", "AMD", "ARM", "AI", "UBS", "SPDR"}:
                        words.append(upper)
                    elif upper == "ISHARES":
                        words.append("iShares")
                    else:
                        words.append(word.capitalize())
                display = " ".join(words)
        else:
            display = cleaned

    ticker = (identifier or "").strip().upper()
    looks_like_ticker = bool(
        ticker
        and len(ticker) <= 6
        and re.fullmatch(r"[A-Z0-9.\-]+", ticker)
    )
    if looks_like_ticker and ticker.casefold() not in display.casefold():
        return f"{display} ({ticker})"
    return display


def _asset_attention_lines(operational: Any) -> tuple[str, ...]:
    priority = {
        "deep_drawdown": 4,
        "relevant_drawdown": 4,
        "high_cvar": 3,
        "elevated_cvar": 3,
        "high_var": 2,
        "elevated_var": 2,
        "high_volatility": 1,
        "elevated_volatility": 1,
    }
    grouped: dict[str, dict[str, Any]] = {}

    for index, attention in enumerate(tuple(getattr(operational, "attention_items", ()) or ())):
        if getattr(attention, "source", None) != "QUANTITATIVE":
            continue

        label = (getattr(attention, "asset_label", None) or "").strip()
        identifier = (getattr(attention, "identifier", None) or "").strip()
        asset = _display_asset_label(label, identifier)
        if not asset:
            continue

        reason = getattr(attention, "reason", "")
        entry = grouped.setdefault(asset, {"score": 0, "index": index, "reasons": set()})
        entry["score"] = max(entry["score"], priority.get(reason, 0))
        entry["reasons"].add(reason)

    def description(reasons: set[str]) -> str:
        has_drawdown = bool(reasons & {"deep_drawdown", "relevant_drawdown"})
        has_tail = bool(reasons & {"high_cvar", "elevated_cvar", "high_var", "elevated_var"})
        has_volatility = bool(reasons & {"high_volatility", "elevated_volatility"})

        if has_drawdown and (has_tail or has_volatility):
            return (
                "queda recente relevante, acompanhada de oscilações acima do normal; "
                "merece acompanhamento para verificar se o movimento persiste"
            )
        if has_drawdown:
            return "queda recente relevante; merece acompanhamento para verificar se o movimento persiste"
        if has_tail and has_volatility:
            return "quedas recentes acima do normal e oscilações elevadas; merece acompanhamento mais próximo"
        if has_tail:
            return "quedas recentes acima do normal; merece acompanhamento mais próximo"
        if has_volatility:
            return "oscilações recentes elevadas; merece acompanhamento"
        return "comportamento recente que merece acompanhamento"

    ranked = sorted(
        grouped.items(),
        key=lambda item: (-int(item[1]["score"]), int(item[1]["index"])),
    )
    return tuple(
        f"{asset} — {description(values['reasons'])}."
        for asset, values in ranked[:3]
    )

def _final_items(structural: Any, quantitative: Any, operational: Any) -> tuple[PatrimonialAnalysisItem, ...]:
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
                f"Nenhuma posição domina a carteira: a maior representa {top_1 * 100:.1f}% em {currency}."
            )
        if top_5 and top_5 < 0.55:
            strengths.append(
                f"As 5 maiores posições somam {top_5 * 100:.1f}% em {currency}; o restante está distribuído entre as demais posições."
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
                f"O patrimônio está distribuído entre {len(positive)} classes; "
                f"a maior é {_economic_class_label(top_class)}, com {_pct(top_amount / total)} em {currency}."
            )

    if operational.structural_level == "Alta" and len(attention) < 3:
        attention.append("Estrutura da carteira — concentração ou cobertura de dados também merece avaliação.")
    if structural.warnings and len(attention) < 3:
        attention.append("Qualidade dos dados — há informações que precisam ser conferidas antes de qualquer providência.")

    strengths = strengths[:3]
    attention = attention[:3]
    primary_asset = ""
    if attention:
        primary_asset = attention[0].split(" — ", 1)[0].rstrip(".:")

    return (
        PatrimonialAnalysisItem(
            title="O que está bem",
            reading=" • ".join(strengths) if strengths else "Sem destaque positivo adicional.",
            evidence=("carteira atual", "histórico de mercado disponível"),
            confidence="Média",
        ),
        PatrimonialAnalysisItem(
            title="O que merece atenção",
            reading=" • ".join(attention) if attention else "Nenhum problema relevante foi confirmado com os dados atuais.",
            evidence=("carteira atual", "histórico de mercado disponível"),
            confidence="Média",
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
