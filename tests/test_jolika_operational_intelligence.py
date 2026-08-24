from dataclasses import replace
from decimal import Decimal

import pytest

from backend.jolika_operational_intelligence import (
    build_jolika_operational_intelligence,
)
from backend.jolika_portfolio_intelligence import (
    build_jolika_portfolio_intelligence,
)
from backend.models import (
    EconomicAssetClass,
    PortfolioOwner,
    PortfolioPosition,
)
from backend.ubs_operational_intelligence import (
    UBSOperationalAttention,
    UBSOperationalIntelligence,
)
from backend.santander_operational_intelligence import (
    SantanderOperationalAttention,
    SantanderOperationalIntelligence,
)


def position(
    institution: str,
    identifier: str,
    *,
    market_value: str = "100",
):
    return PortfolioPosition(
        institution=institution,
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_name=identifier,
        identifier=identifier,
        identifier_type="TICKER",
        asset_class="Equity",
        economic_asset_class=EconomicAssetClass.EQUITIES,
        asset_subclass=None,
        currency="USD",
        market_value=Decimal(market_value),
        quantity=None,
        unit_price=None,
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )


def ubs(
    *,
    structural_level="Baixa",
    quantitative_level="Baixa",
    overall_level="Baixa",
    analyzed=1,
    unavailable=0,
    attention=(),
):
    return UBSOperationalIntelligence(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        structural_level=structural_level,
        quantitative_level=quantitative_level,
        overall_level=overall_level,
        attention_items=attention,
        analyzed_quantitative_positions=analyzed,
        unavailable_quantitative_positions=unavailable,
        executive_reading="UBS reading",
    )


def santander(
    *,
    structural_level="Baixa",
    quantitative_level="Baixa",
    overall_level="Baixa",
    analyzed=1,
    unavailable=0,
    attention=(),
):
    return SantanderOperationalIntelligence(
        institution="Santander",
        owner=PortfolioOwner.JOLIKA,
        structural_level=structural_level,
        quantitative_level=quantitative_level,
        overall_level=overall_level,
        attention_items=attention,
        analyzed_quantitative_positions=analyzed,
        unavailable_quantitative_positions=unavailable,
        executive_reading="Santander reading",
    )


def diversified_structural():
    return build_jolika_portfolio_intelligence(
        [
            position("UBS", "AAA"),
            position("UBS", "BBB"),
            position("Santander", "CCC"),
            position("Santander", "DDD"),
        ]
    )


def test_builds_consolidated_operational_intelligence():
    structural = diversified_structural()

    result = build_jolika_operational_intelligence(
        structural,
        [
            ubs(),
            santander(),
        ],
    )

    assert result.owner is PortfolioOwner.JOLIKA
    assert structural.priority.level == "Média"
    assert result.structural_level == structural.priority.level
    assert result.institutional_level == "Baixa"
    assert result.overall_level == "Média"
    assert result.analyzed_quantitative_positions == 2
    assert result.unavailable_quantitative_positions == 0

    assert tuple(
        item.institution
        for item in result.institution_assessments
    ) == (
        "Santander",
        "UBS",
    )


def test_strongest_institution_controls_institutional_level():
    structural = diversified_structural()

    result = build_jolika_operational_intelligence(
        structural,
        [
            ubs(overall_level="Alta"),
            santander(overall_level="Média"),
        ],
    )

    assert result.institutional_level == "Alta"
    assert result.overall_level == "Alta"


def test_consolidated_structure_can_control_overall_level():
    structural = build_jolika_portfolio_intelligence(
        [
            position("UBS", "AAA", market_value="900"),
            position("Santander", "BBB", market_value="100"),
        ]
    )

    result = build_jolika_operational_intelligence(
        structural,
        [
            ubs(),
            santander(),
        ],
    )

    assert structural.priority.level == "Alta"
    assert result.structural_level == "Alta"
    assert result.overall_level == "Alta"


def test_quantitative_attention_preserves_institution_origin():
    structural = diversified_structural()

    result = build_jolika_operational_intelligence(
        structural,
        [
            ubs(
                overall_level="Alta",
                quantitative_level="Alta",
                attention=(
                    UBSOperationalAttention(
                        source="QUANTITATIVE",
                        level="Alta",
                        reason="high_volatility",
                        identifier="AAA",
                        asset_label="AAA",
                    ),
                ),
            ),
            santander(
                overall_level="Média",
                quantitative_level="Média",
                attention=(
                    SantanderOperationalAttention(
                        source="QUANTITATIVE",
                        level="Média",
                        reason="relevant_drawdown",
                        identifier="CCC",
                        asset_label="CCC",
                    ),
                ),
            ),
        ],
    )

    assert any(
        item.institution == "UBS"
        and item.identifier == "AAA"
        and item.reason == "high_volatility"
        for item in result.attention_items
    )

    assert any(
        item.institution == "Santander"
        and item.identifier == "CCC"
        and item.reason == "relevant_drawdown"
        for item in result.attention_items
    )


def test_quantitative_counts_are_summed_without_recalculation():
    structural = diversified_structural()

    result = build_jolika_operational_intelligence(
        structural,
        [
            ubs(
                analyzed=7,
                unavailable=2,
            ),
            santander(
                analyzed=5,
                unavailable=1,
            ),
        ],
    )

    assert result.analyzed_quantitative_positions == 12
    assert result.unavailable_quantitative_positions == 3


def test_no_institutional_intelligence_is_explicit():
    structural = diversified_structural()

    result = build_jolika_operational_intelligence(
        structural,
        [],
    )

    assert result.institutional_level == "Baixa"
    assert result.analyzed_quantitative_positions == 0
    assert (
        result.executive_reading
        == "Ainda não há instituições com inteligência operacional "
        "disponível para completar a leitura consolidada da Jolika."
    )


def test_no_quantitative_history_remains_visible():
    structural = diversified_structural()

    result = build_jolika_operational_intelligence(
        structural,
        [
            ubs(
                analyzed=0,
                unavailable=2,
            ),
            santander(
                analyzed=0,
                unavailable=2,
            ),
        ],
    )

    assert result.analyzed_quantitative_positions == 0
    assert result.unavailable_quantitative_positions == 4
    assert "histórico de mercado suficiente" in result.executive_reading


def test_rejects_non_jolika_structural_owner():
    structural = diversified_structural()

    invalid = replace(
        structural,
        owner=PortfolioOwner.NEI,
    )

    with pytest.raises(
        ValueError,
        match="structural intelligence must belong to JOLIKA",
    ):
        build_jolika_operational_intelligence(
            invalid,
            [ubs()],
        )


def test_rejects_non_jolika_institutional_owner():
    structural = diversified_structural()

    invalid = replace(
        ubs(),
        owner=PortfolioOwner.NEI,
    )

    with pytest.raises(
        ValueError,
        match="must belong to JOLIKA",
    ):
        build_jolika_operational_intelligence(
            structural,
            [invalid],
        )


def test_rejects_unsupported_operational_type():
    structural = diversified_structural()

    with pytest.raises(
        TypeError,
        match="supported operational intelligence",
    ):
        build_jolika_operational_intelligence(
            structural,
            [object()],
        )


def test_result_is_deterministic_regardless_of_institution_order():
    structural = diversified_structural()

    first = build_jolika_operational_intelligence(
        structural,
        [
            ubs(overall_level="Alta"),
            santander(overall_level="Média"),
        ],
    )

    second = build_jolika_operational_intelligence(
        structural,
        [
            santander(overall_level="Média"),
            ubs(overall_level="Alta"),
        ],
    )

    assert first == second
