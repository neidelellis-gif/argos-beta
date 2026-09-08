from __future__ import annotations

import pytest

from backend.patrimonial_analysis_method import (
    PATRIMONIAL_ANALYSIS_STAGE_KEYS,
    PatrimonialAnalysisReport,
    PatrimonialAnalysisStage,
    build_patrimonial_analysis_report,
    unavailable_stage,
)


def _stage(key: str, title: str) -> PatrimonialAnalysisStage:
    return PatrimonialAnalysisStage(key=key, title=title, summary=title)


def test_report_preserves_official_five_stage_order() -> None:
    report = build_patrimonial_analysis_report(
        universe="UBS",
        scope="institution",
        diagnosis=_stage("diagnosis", "Diagnóstico da carteira"),
        composition=_stage("composition", "Análise da composição"),
        master_assumptions=_stage(
            "master_assumptions",
            "Aderência às Premissas Mestres da JOLIKA",
        ),
        market_context=_stage("market_context", "Carteira × ambiente de mercado"),
        final_diagnosis=_stage("final_diagnosis", "Diagnóstico final"),
    )

    payload = report.to_dict()

    assert payload["method"] == "ARGOS_PATRIMONIAL_5_STAGE_V1"
    assert payload["universe"] == "UBS"
    assert payload["scope"] == "institution"
    assert tuple(stage["key"] for stage in payload["stages"]) == PATRIMONIAL_ANALYSIS_STAGE_KEYS


def test_report_rejects_missing_or_reordered_stages() -> None:
    with pytest.raises(ValueError, match="five official stages"):
        PatrimonialAnalysisReport(
            universe="JOLIKA",
            scope="consolidated",
            stages=(
                _stage("composition", "Análise da composição"),
                _stage("diagnosis", "Diagnóstico da carteira"),
            ),
        )


def test_unavailable_stage_declares_limitation_once_instead_of_inventing_result() -> None:
    stage = unavailable_stage(
        "market_context",
        "Carteira × ambiente de mercado",
        "Contexto de mercado atual não disponível.",
    )

    assert stage.status == "limited"
    assert stage.summary == "Contexto de mercado atual não disponível."
    assert stage.items == ()
