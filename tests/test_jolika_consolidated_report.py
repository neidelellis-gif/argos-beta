"""Regression tests for the consolidated JOLIKA executive report."""
from decimal import Decimal
from types import SimpleNamespace as NS

from backend.jolika_patrimonial_report import _composition_items, _final_items


def structural():
    return NS(
        coverage=NS(consolidated_asset_count=64, assets_with_economic_class=64),
        concentration_by_currency=(
            NS(currency="USD", top_1_weight=Decimal("0.082"),
               top_3_weight=Decimal("0.21"), top_5_weight=Decimal("0.345")),
        ),
        economic_allocation_by_currency=(
            ("USD", (
                (NS(value="Renda Fixa"), Decimal("36.1")),
                (NS(value="ETFs"), Decimal("22.0")),
                (NS(value="Fundos"), Decimal("18.0")),
                (NS(value="Ações"), Decimal("13.9")),
                (NS(value="Caixa"), Decimal("10.0")),
            )),
        ),
        duplicate_exposures=(),
    )


def operational():
    return NS(
        structural_level="Baixa",
        overall_level="Alta",
        unavailable_quantitative_positions=4,
        attention_items=(
            NS(source="QUANTITATIVE", asset_label="CONSTELLATION ENERGY CORPORATION",
               identifier="US21037T1097", reason="deep_drawdown"),
            NS(source="QUANTITATIVE", asset_label="GE VERNOVA INC",
               identifier="US36828A1016", reason="deep_drawdown"),
            NS(source="QUANTITATIVE", asset_label="ISHARES BITCOIN TRUST ETF",
               identifier="US46438F1012", reason="relevant_drawdown"),
            NS(source="QUANTITATIVE", asset_label="Outro Ativo",
               identifier="OUTR", reason="high_volatility"),
        ),
    )


def test_consolidated_summary_is_factual_and_names_top_three_assets():
    items = _final_items(structural(), operational())
    assert tuple(item.title for item in items) == (
        "O que está bem", "O que merece atenção", "Encaminhamento"
    )

    strengths = items[0].reading
    assert "8.2%" in strengths
    assert "34.5%" in strengths
    assert "5 classes" in strengths

    attention = items[1].reading
    assert "Constellation Energy" in attention
    assert "GE Vernova" in attention
    assert "iShares Bitcoin Trust" in attention
    assert "US21037T1097" not in attention
    assert "Outro Ativo" not in attention

    forwarding = items[2].reading
    assert "O principal ponto de atenção hoje é Constellation Energy" in forwarding
    assert "Banker" in forwarding
    assert "recomend" not in forwarding.casefold()


def test_consolidated_composition_exposes_largest_position_for_executive_metric():
    visible = " ".join(item.reading for item in _composition_items(structural()))
    assert "Maior posição 8.2%" in visible
