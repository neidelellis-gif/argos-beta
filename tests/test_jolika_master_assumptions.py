from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from backend.jolika_master_assumptions import (
    JOLIKA_MASTER_ASSUMPTIONS_VERSION,
    get_jolika_master_assumptions,
)
from backend.jolika_master_assumptions_analysis import build_master_assumptions_stage


def _structural() -> SimpleNamespace:
    concentration = SimpleNamespace(
        currency="USD",
        top_1_weight=Decimal("0.054"),
        top_3_weight=Decimal("0.14"),
        top_5_weight=Decimal("0.21"),
    )
    allocation = (
        (
            "USD",
            (
                (SimpleNamespace(value="EQUITY"), Decimal("60")),
                (SimpleNamespace(value="FIXED_INCOME"), Decimal("40")),
            ),
        ),
    )
    return SimpleNamespace(
        concentration_by_currency=(concentration,),
        economic_allocation_by_currency=allocation,
    )


def test_official_jolika_master_assumptions_are_versioned_and_fixed_in_order() -> None:
    assumptions = get_jolika_master_assumptions()

    assert JOLIKA_MASTER_ASSUMPTIONS_VERSION == "1.0"
    assert tuple(item.key for item in assumptions) == (
        "patrimonial_objective",
        "expected_return",
        "acceptable_risk",
        "allocation_diversification",
        "decision_rules",
    )
    assert len(assumptions) == 5
    assert "12% ao ano em USD" in assumptions[1].text
    assert "não como limite superior" in assumptions[1].text


def test_stage_three_becomes_available_without_inventing_missing_return_or_decision_history() -> None:
    stage = build_master_assumptions_stage(
        _structural(),
        quantitative=SimpleNamespace(
            analyzed_position_count=8,
            unavailable_position_count=2,
        ),
        operational=SimpleNamespace(overall_level="Baixa"),
    )

    assert stage.key == "master_assumptions"
    assert stage.status == "available"
    assert len(stage.items) == 5
    assert stage.title == "Sua carteira e seus objetivos"
    assert tuple(item.title for item in stage.items) == (
        "Seu objetivo",
        "O retorno que buscamos",
        "Quanto risco faz sentido",
        "Como o dinheiro está distribuído",
        "Como vamos tomar decisões",
    )

    return_item = stage.items[1]
    decision_item = stage.items[4]
    assert "12% ao ano em USD" in return_item.reading
    assert "precisamos acompanhar o desempenho ao longo do tempo" in return_item.reading
    assert "não queremos mudar a carteira só porque um investimento subiu ou caiu" in decision_item.reading.casefold()
    assert all("Regras da JOLIKA v1.0" in item.evidence[0] for item in stage.items)


def test_consolidated_stage_can_use_structural_evidence_without_fake_quantitative_coverage() -> None:
    stage = build_master_assumptions_stage(
        _structural(),
        operational=SimpleNamespace(overall_level="Média"),
    )

    assert stage.status == "available"
    risk_item = stage.items[2]
    allocation_item = stage.items[3]
    assert "faltam dados do comportamento dos investimentos" in risk_item.reading
    assert "2 tipos principais de investimento" in allocation_item.reading
    assert "a maior posição representa 5.4% da carteira em USD" in allocation_item.reading


def test_stage_three_avoids_finance_jargon_in_visible_copy() -> None:
    stage = build_master_assumptions_stage(
        _structural(),
        quantitative=SimpleNamespace(
            analyzed_position_count=8,
            unavailable_position_count=2,
        ),
        operational=SimpleNamespace(overall_level="Baixa"),
    )

    visible = " ".join([stage.title, stage.summary] + [item.title + " " + item.reading for item in stage.items])
    assert "aderência" not in visible.casefold()
    assert "premissas mestres" not in visible.casefold()
    assert "classe(s) econômica(s)" not in visible.casefold()
