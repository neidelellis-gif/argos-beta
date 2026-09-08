"""Evidence-based Stage 3 analysis against the official JOLIKA master assumptions."""

from __future__ import annotations

from typing import Any

from backend.jolika_master_assumptions import (
    JOLIKA_MASTER_ASSUMPTIONS_APPROVED_ON,
    JOLIKA_MASTER_ASSUMPTIONS_SOURCE,
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
        f"maior posição em {currency}: {_pct(getattr(strongest, 'top_1_weight', None))}; "
        f"Top 3: {_pct(getattr(strongest, 'top_3_weight', None))}; "
        f"Top 5: {_pct(getattr(strongest, 'top_5_weight', None))}"
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
        f"Premissas Mestres JOLIKA v{JOLIKA_MASTER_ASSUMPTIONS_VERSION}",
        f"aprovadas em {JOLIKA_MASTER_ASSUMPTIONS_APPROVED_ON}",
        JOLIKA_MASTER_ASSUMPTIONS_SOURCE,
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
            title=assumptions["patrimonial_objective"].title,
            reading=(
                "Aderência parcial. A fotografia atual permite verificar diversificação e concentração, "
                f"mas não confirma sozinha crescimento real do patrimônio. Evidência estrutural atual: {concentration}."
            ),
            evidence=_source_evidence() + ("carteira importada", "métricas estruturais do ARGOS"),
            confidence="Parcial",
        ),
        PatrimonialAnalysisItem(
            title=assumptions["expected_return"].title,
            reading=(
                "Aderência ainda não mensurável pela fotografia atual. A meta-base de 12% a.a. em USD "
                "é referência, não piso nem teto; sua avaliação exige série de desempenho da carteira e "
                "comparação conjunta com risco, teses e ambiente de mercado."
            ),
            evidence=_source_evidence() + ("premissa oficial de retorno",),
            confidence="Alta sobre a limitação",
        ),
        PatrimonialAnalysisItem(
            title=assumptions["acceptable_risk"].title,
            reading=(
                "Aderência parcial. O ARGOS consegue observar concentração e cobertura histórica de risco, "
                f"mas a proporcionalidade entre risco e retorno esperado depende da qualidade das teses. "
                f"Cobertura quantitativa disponível: {analyzed} posição(ões) analisada(s) e {unavailable} sem cobertura suficiente."
                if quantitative is not None
                else (
                    "Aderência parcial. O ARGOS consegue observar concentração estrutural, mas a proporcionalidade "
                    "entre risco e retorno esperado depende de dados quantitativos e da qualidade das teses."
                )
            ),
            evidence=_source_evidence() + ("métricas estruturais do ARGOS",),
            confidence="Parcial",
        ),
        PatrimonialAnalysisItem(
            title=assumptions["allocation_diversification"].title,
            reading=(
                f"Aderência observável parcialmente. Foram identificadas {class_count} classe(s) econômica(s); {concentration}. "
                "A premissa não define um limite mecânico de concentração, porque diversificação não deve diluir as melhores oportunidades."
            ),
            evidence=_source_evidence() + ("classificação econômica", "concentração calculada pelo ARGOS"),
            confidence="Média",
        ),
        PatrimonialAnalysisItem(
            title=assumptions["decision_rules"].title,
            reading=(
                "Aderência não mensurável apenas pela posição atual. Para avaliar esta premissa, o ARGOS precisa "
                "relacionar histórico das decisões, evolução das teses, risco-retorno e impacto de cada decisão sobre a carteira."
            ),
            evidence=_source_evidence() + ("carteira atual não contém histórico de decisão",),
            confidence="Alta sobre a limitação",
        ),
    )

    summary = (
        "As cinco Premissas Mestres da JOLIKA estão formalizadas e passam a integrar a análise. "
        "A aderência é classificada somente onde há evidência; metas de retorno, qualidade das teses e processo decisório "
        "não são presumidos a partir de uma fotografia da carteira."
    )
    if overall_level:
        summary += f" Leitura operacional atual do universo analisado: {overall_level}."

    return PatrimonialAnalysisStage(
        key="master_assumptions",
        title="Aderência às Premissas Mestres da JOLIKA",
        summary=summary,
        items=items,
        status="available",
    )
