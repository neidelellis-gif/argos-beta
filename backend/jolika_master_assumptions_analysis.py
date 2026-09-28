"""Evidence-based Stage 3 analysis against the official JOLIKA master assumptions."""

from __future__ import annotations

from typing import Any

from backend.jolika_master_assumptions import (
    JOLIKA_MASTER_ASSUMPTIONS_APPROVED_ON,
    JOLIKA_MASTER_ASSUMPTIONS_VERSION,
    get_jolika_master_assumptions,
)
from backend.patrimonial_analysis_method import (
    PatrimonialAnalysisItem,
    PatrimonialAnalysisStage,
)


def _pct(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _max_concentration(structural: Any) -> str:
    concentrations = tuple(getattr(structural, "concentration_by_currency", ()) or ())
    if not concentrations:
        return "concentração não disponível"
    strongest = max(
        concentrations,
        key=lambda item: float(getattr(item, "top_1_weight", 0) or 0),
    )
    currency = getattr(strongest, "currency", "moeda não identificada")
    return (
        f"a maior posição representa {_pct(getattr(strongest, 'top_1_weight', None))} da carteira em {currency}; "
        f"as 3 maiores, {_pct(getattr(strongest, 'top_3_weight', None))}; "
        f"e as 5 maiores, {_pct(getattr(strongest, 'top_5_weight', None))}"
    )


def _economic_class_count(structural: Any) -> int:
    classes: set[str] = set()
    for _, allocation in tuple(getattr(structural, "economic_allocation_by_currency", ()) or ()):
        for asset_class, _ in allocation:
            classes.add(getattr(asset_class, "value", str(asset_class)))
    return len(classes)


def _quantitative_coverage(quantitative: Any | None) -> tuple[int, int]:
    if quantitative is None:
        return 0, 0
    analyzed = int(getattr(quantitative, "analyzed_position_count", 0) or 0)
    unavailable = int(getattr(quantitative, "unavailable_position_count", 0) or 0)
    return analyzed, unavailable


def _source_evidence() -> tuple[str, ...]:
    return (
        f"Regras da JOLIKA v{JOLIKA_MASTER_ASSUMPTIONS_VERSION}, aprovadas em {JOLIKA_MASTER_ASSUMPTIONS_APPROVED_ON}",
    )


def build_master_assumptions_stage(
    structural: Any,
    *,
    quantitative: Any | None = None,
    operational: Any | None = None,
) -> PatrimonialAnalysisStage:
    """Apply the official reference without inventing unavailable evidence.

    The stage is available because the master assumptions are now formalized.
    Individual conclusions may remain partial when the imported snapshot cannot
    measure a premise such as realized return or decision quality.
    """

    assumptions = {item.key: item for item in get_jolika_master_assumptions()}
    concentration = _max_concentration(structural)
    class_count = _economic_class_count(structural)
    analyzed, unavailable = _quantitative_coverage(quantitative)
    overall_level = getattr(operational, "overall_level", None)

    items = (
        PatrimonialAnalysisItem(
            title="Seu objetivo",
            reading=(
                "A carteira está distribuída entre diferentes tipos de investimento e nenhuma posição domina o conjunto. "
                f"Hoje, {concentration}. Isso é um bom ponto de partida para proteger e fazer o patrimônio crescer, "
                "mas precisamos acompanhar a evolução ao longo do tempo para saber se esse objetivo está sendo alcançado."
            ),
            evidence=_source_evidence() + ("carteira atual",),
            confidence="Parcial",
        ),
        PatrimonialAnalysisItem(
            title="O retorno que buscamos",
            reading=(
                "A referência da JOLIKA continua sendo buscar cerca de 12% ao ano em USD. "
                "Uma fotografia de hoje não mostra se estamos chegando lá; precisamos acompanhar o desempenho ao longo do tempo "
                "e o risco assumido para alcançar esse resultado."
            ),
            evidence=_source_evidence() + ("meta de retorno da JOLIKA",),
            confidence="Alta sobre a limitação",
        ),
        PatrimonialAnalysisItem(
            title="Quanto risco faz sentido",
            reading=(
                (
                    "A JOLIKA aceita oscilações maiores quando existe uma boa razão para isso. "
                    "Além de olhar como o dinheiro está distribuído, usamos o histórico de mercado quando ele é confiável. "
                    "Quando esse histórico ainda é curto, não forçamos uma conclusão: o investimento continua fazendo parte da análise pelo papel que ocupa na carteira."
                )
                if quantitative is not None
                else (
                    "A JOLIKA aceita oscilações maiores quando existe uma boa razão para isso. "
                    "Hoje conseguimos avaliar bem como o dinheiro está distribuído. "
                    "À medida que o histórico de mercado aumenta, vamos acrescentando essa informação sem deixar nenhum investimento fora da leitura da carteira."
                )
            ),
            evidence=_source_evidence() + ("histórico disponível dos investimentos",),
            confidence="Parcial",
        ),
        PatrimonialAnalysisItem(
            title="Como o dinheiro está distribuído",
            reading=(
                f"O dinheiro está dividido entre {class_count} tipos principais de investimento; {concentration}. "
                "A ideia é evitar depender demais de poucos investimentos sem espalhar o patrimônio só por espalhar."
            ),
            evidence=_source_evidence() + ("carteira atual",),
            confidence="Média",
        ),
        PatrimonialAnalysisItem(
            title="Como vamos tomar decisões",
            reading=(
                "Não queremos mudar a carteira só porque um investimento subiu ou caiu. "
                "As decisões devem considerar se a ideia por trás do investimento continua fazendo sentido, "
                "o risco envolvido e o efeito sobre o conjunto da carteira. "
                "Ainda precisamos construir mais histórico das decisões para avaliar esse ponto melhor."
            ),
            evidence=_source_evidence() + ("histórico de decisões ainda incompleto",),
            confidence="Alta sobre a limitação",
        ),
    )

    summary = (
        "Queremos responder a uma pergunta simples: esta carteira continua fazendo sentido para o que a JOLIKA quer alcançar? "
        "Hoje já dá para enxergar bem como o dinheiro está distribuído. Para avaliar retorno e a qualidade das decisões, "
        "ainda precisamos de mais histórico."
    )

    return PatrimonialAnalysisStage(
        key="master_assumptions",
        title="Sua carteira e seus objetivos",
        summary=summary,
        items=items,
        status="available",
    )
