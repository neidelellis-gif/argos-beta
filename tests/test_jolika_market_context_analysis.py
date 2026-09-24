from datetime import datetime, timezone
from decimal import Decimal

from backend.important_facts import FactCandidate, FactCategory, FactImportance
from backend.jolika_market_context_analysis import (
    analyze_jolika_market_context,
    build_market_context_stage,
)
from backend.models import PortfolioOwner, PortfolioPosition


def _position(identifier: str = "NVDA") -> PortfolioPosition:
    return PortfolioPosition(
        owner=PortfolioOwner.JOLIKA,
        institution="UBS",
        account=None,
        asset_class="Equity",
        asset_subclass=None,
        asset_name="NVIDIA",
        identifier=identifier,
        identifier_type="TICKER",
        quantity=None,
        unit_price=None,
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="ubs.csv",
    )


def _fact(*, related_assets=("NVDA",), importance=FactImportance.HIGH) -> FactCandidate:
    return FactCandidate(
        id="fact-1",
        title="Fato relevante para NVIDIA",
        description="Descrição factual do evento.",
        source="Fonte oficial",
        published_at=datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
        importance=importance,
        category=FactCategory.MARKETS,
        related_assets=related_assets,
    )


def test_market_context_relates_fact_to_real_portfolio_exposure_without_direction() -> None:
    items = analyze_jolika_market_context((_position(),), (_fact(),))

    assert len(items) == 1
    assert items[0].affected_assets == ("NVDA",)
    assert items[0].intensity == "Alta"
    assert items[0].source == "Fonte oficial"
    assert items[0].impact_direction == "Não determinada"


def test_market_context_stage_is_limited_when_no_fact_relates_to_portfolio() -> None:
    stage = build_market_context_stage(
        (_position(),),
        (_fact(related_assets=("AAPL",)),),
    )

    assert stage.key == "market_context"
    assert stage.status == "limited"
    assert stage.items == ()
    assert "não atribuirá direção de impacto" in stage.summary


def test_market_context_stage_exposes_source_evidence_and_intensity() -> None:
    stage = build_market_context_stage(
        (_position(),),
        (_fact(importance=FactImportance.MEDIUM),),
    )

    assert stage.status == "available"
    assert len(stage.items) == 1
    assert "Relevância/intensidade: Moderada" in stage.items[0].reading
    assert "Direção do impacto: Não determinada" in stage.items[0].reading
    assert stage.items[0].evidence == (
        "Fonte: Fonte oficial",
        "Descrição factual do evento.",
    )


def test_macro_fact_enters_stage_as_portfolio_level_context_without_asset_match() -> None:
    macro = FactCandidate(
        id="macro-1",
        title="Federal Reserve publishes monetary policy update",
        description="Official monetary policy information.",
        source="Federal Reserve",
        published_at=datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
        importance=FactImportance.HIGH,
        category=FactCategory.ECONOMY,
    )

    stage = build_market_context_stage((_position(),), (macro,))

    assert stage.status == "available"
    assert len(stage.items) == 1
    assert stage.items[0].title == "Macro e juros"
    assert "sem atribuição automática a cada posição" in stage.items[0].reading
    assert stage.items[0].evidence == (
        "Fonte: Federal Reserve",
        "Official monetary policy information.",
    )
