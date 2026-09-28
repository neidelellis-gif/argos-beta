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
    assert "Exposições da carteira para acompanhamento deste contexto: Ações." in stage.items[0].reading
    assert "direção do impacto não é inferida automaticamente" in stage.items[0].reading
    assert stage.items[0].evidence == (
        "Fonte: Federal Reserve",
        "Official monetary policy information.",
    )


def test_macro_context_names_observed_fixed_income_exposure_without_inferring_direction() -> None:
    macro = FactCandidate(
        id="macro-exposure",
        title="Federal Reserve publishes monetary policy update",
        description="Official monetary policy information.",
        source="Federal Reserve",
        published_at=datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
        importance=FactImportance.HIGH,
        category=FactCategory.ECONOMY,
    )
    fixed_income = PortfolioPosition(
        owner=PortfolioOwner.JOLIKA,
        institution="UBS",
        account=None,
        asset_class="Fixed Income",
        asset_subclass=None,
        asset_name="US Treasury Note",
        identifier="UST10Y",
        identifier_type="TICKER",
        quantity=None,
        unit_price=None,
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="ubs.csv",
    )

    stage = build_market_context_stage((fixed_income,), (macro,))

    assert stage.status == "available"
    assert "Renda fixa" in stage.items[0].reading
    assert "relação é de monitoramento" in stage.items[0].reading
    assert "Direção do impacto: Não determinada" in stage.items[0].reading


def test_google_news_rate_headline_stays_market_discovery_not_macro_context() -> None:
    discovery = FactCandidate(
        id="google-rate",
        title="Fed rate hike odds hit 70%: Gold, Treasury yields signal",
        description="Discovery headline about GLD.",
        source="Google News",
        published_at=datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
        importance=FactImportance.MEDIUM,
        category=FactCategory.MARKETS,
        related_assets=("GLD",),
    )
    gld = _position("GLD")

    stage = build_market_context_stage((gld,), (discovery,))

    assert stage.status == "available"
    assert len(stage.items) == 1
    assert stage.items[0].title == "Mercados"
    assert "GLD" in stage.items[0].reading


def test_macro_selection_prioritizes_federal_reserve_over_input_order() -> None:
    bls = FactCandidate(
        id="bls-cpi",
        title="Consumer Price Index for All Urban Consumers",
        description="Consumer Price Index: 334.980.",
        source="BLS",
        published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        importance=FactImportance.MEDIUM,
        category=FactCategory.ECONOMY,
    )
    fed = FactCandidate(
        id="fed-fomc",
        title="Federal Reserve issues FOMC statement",
        description="Official monetary policy statement.",
        source="Federal Reserve",
        published_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        importance=FactImportance.HIGH,
        category=FactCategory.ECONOMY,
    )

    items = analyze_jolika_market_context((_position(),), (bls, fed))

    assert items[0].source == "Federal Reserve"


def test_cpi_macro_context_does_not_claim_every_portfolio_class_is_relevant() -> None:
    cpi = FactCandidate(
        id="bls-cpi-classes",
        title="Consumer Price Index for All Urban Consumers",
        description="Consumer Price Index: 334.980.",
        source="BLS",
        published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        importance=FactImportance.MEDIUM,
        category=FactCategory.ECONOMY,
    )
    positions = (
        _position(),
        PortfolioPosition(
            owner=PortfolioOwner.JOLIKA,
            institution="UBS",
            account=None,
            asset_class="Fixed Income",
            asset_subclass=None,
            asset_name="US Treasury Note",
            identifier="UST10Y",
            identifier_type="TICKER",
            quantity=None,
            unit_price=None,
            market_value=Decimal("100"),
            currency="USD",
            portfolio_weight=None,
            reference_date=None,
            source_file="ubs.csv",
        ),
        PortfolioPosition(
            owner=PortfolioOwner.JOLIKA,
            institution="UBS",
            account=None,
            asset_class="Crypto",
            asset_subclass=None,
            asset_name="Bitcoin",
            identifier="BTC",
            identifier_type="TICKER",
            quantity=None,
            unit_price=None,
            market_value=Decimal("100"),
            currency="USD",
            portfolio_weight=None,
            reference_date=None,
            source_file="ubs.csv",
        ),
    )

    stage = build_market_context_stage(positions, (cpi,))

    assert "Renda fixa" in stage.items[0].reading
    assert "Ações" in stage.items[0].reading
    assert "Cripto" not in stage.items[0].reading
    assert "Direção do impacto: Não determinada" in stage.items[0].reading


def test_stage4_uses_portuguese_executive_summary_for_fed_projection() -> None:
    fed = FactCandidate(
        id="fed-projection-pt",
        title="Federal Reserve Board and Federal Open Market Committee release economic projections from the September FOMC meeting",
        description="Official economic projections.",
        source="Federal Reserve",
        published_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        importance=FactImportance.HIGH,
        category=FactCategory.ECONOMY,
    )

    stage = build_market_context_stage((_position(),), (fed,))

    assert stage.status == "available"
    assert stage.items[0].reading.startswith(
        "O Federal Reserve divulgou novas projeções econômicas após a reunião do FOMC."
    )
    assert "release economic projections" not in stage.items[0].reading


def test_stage4_deduplicates_repeated_source_in_evidence() -> None:
    projection = FactCandidate(
        id="fed-projection-source",
        title="Federal Reserve releases economic projections",
        description="Official economic projections.",
        source="Federal Reserve",
        published_at=datetime(2026, 9, 16, 18, tzinfo=timezone.utc),
        importance=FactImportance.HIGH,
        category=FactCategory.ECONOMY,
    )
    statement = FactCandidate(
        id="fed-statement-source",
        title="Federal Reserve issues FOMC statement",
        description="Official FOMC statement.",
        source="Federal Reserve",
        published_at=datetime(2026, 9, 16, 19, tzinfo=timezone.utc),
        importance=FactImportance.HIGH,
        category=FactCategory.ECONOMY,
    )

    stage = build_market_context_stage((_position(),), (projection, statement))

    assert stage.items[0].evidence == (
        "Fonte: Federal Reserve",
        "Official FOMC statement.",
        "Official economic projections.",
    )


def test_stage4_uses_portuguese_market_summary_for_google_news() -> None:
    discovery = FactCandidate(
        id="google-gld-pt",
        title="A former finance chief joins SPDR Gold Trust sponsor board",
        description="Market discovery headline.",
        source="Google News",
        published_at=datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
        importance=FactImportance.MEDIUM,
        category=FactCategory.MARKETS,
        related_assets=("GLD",),
    )

    stage = build_market_context_stage((_position("GLD"),), (discovery,))

    assert stage.items[0].reading.startswith(
        "Foi identificada uma notícia de mercado diretamente relacionada a GLD."
    )
    assert "A former finance chief" not in stage.items[0].reading
