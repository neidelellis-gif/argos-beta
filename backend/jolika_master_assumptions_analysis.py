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
                "Preservar e ampliar o patrimônio. A composição atual, sozinha, "
                "não confirma o resultado ao longo do tempo."
            ),
            evidence=_source_evidence() + ("carteira atual",),
            confidence="Parcial",
        ),
        PatrimonialAnalysisItem(
            title="O retorno que buscamos",
            reading=(
                "Meta-base: 12% ao ano em USD, não um teto. Para avaliar resultado e risco, "
                "precisamos acompanhar o desempenho ao longo do tempo."
            ),
            evidence=_source_evidence() + ("meta de retorno da JOLIKA",),
            confidence="Alta sobre a limitação",
        ),
        PatrimonialAnalysisItem(
            title="Quanto risco faz sentido",
            reading=(
                (
                    "Oscilações maiores exigem retorno potencial proporcional. Com histórico curto, "
                    "o investimento continua fazendo parte da análise pelo seu papel na carteira."
                )
                if quantitative is not None
                else (
                    "Avaliamos a distribuição do patrimônio, sem deixar nenhum investimento fora da leitura da carteira. "
                    "O risco histórico ainda precisa de dados."
                )
            ),
            evidence=_source_evidence() + ("histórico disponível dos investimentos",),
            confidence="Parcial",
        ),
        PatrimonialAnalysisItem(
            title="Como o dinheiro está distribuído",
            reading=(
                f"{class_count} tipos principais de investimento; {concentration}."
            ),
            evidence=_source_evidence() + ("carteira atual",),
            confidence="Média",
        ),
        PatrimonialAnalysisItem(
            title="Como vamos tomar decisões",
            reading=(
                "Não queremos mudar a carteira só porque um investimento subiu ou caiu. "
                "Avaliamos a tese, o risco e o efeito na carteira. Falta histórico para avaliar as decisões."
            ),
            evidence=_source_evidence() + ("histórico de decisões ainda incompleto",),
            confidence="Alta sobre a limitação",
        ),
    )

    summary = (
        "Objetivos e composição da carteira. Retorno e decisões ainda precisam de mais histórico."
    )

    return PatrimonialAnalysisStage(
        key="master_assumptions",
        title="Sua carteira e seus objetivos",
        summary=summary,
        items=items,
        status="available",
    )
