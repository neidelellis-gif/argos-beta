from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from backend.connectors import registry
from backend.daily_brief import DailyBriefEngine, ImportantFact
from backend.daily_portfolio_snapshot import (
    ConsolidatedPortfolioSnapshot,
    DailyPortfolioSnapshot,
    DailyPortfolioSnapshotBuilder,
    DailyPortfolioStatus,
    DailyPortfolioSummary,
)
from backend.important_facts import (
    FactCandidate,
    FactCategory,
    FactImportance,
    FactRelevance,
    ImportantFactsEngine,
    ImportantFactsResult,
)
from backend.portfolio_impact import (
    ImpactLevel,
    ImpactType,
    PortfolioImpact,
    PortfolioImpactEngine,
    PortfolioImpactResult,
)
from backend.models import PortfolioOwner


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def snapshot(
    *,
    institutions: tuple[str, ...] = ("UBS",),
    currencies: tuple[str, ...] = ("USD",),
    classes: tuple[str, ...] = ("Equities",),
    categories: tuple[str, ...] = ("Technology",),
) -> DailyPortfolioSnapshot:
    consolidated = ConsolidatedPortfolioSnapshot(
        position_count=2,
        unique_assets=2,
        gross_value_by_currency=MappingProxyType(
            {currency: Decimal("100") for currency in currencies}
        ),
        positions_by_owner=MappingProxyType({"JOLIKA": 2}),
        positions_by_institution=MappingProxyType(
            {institution: 1 for institution in institutions}
        ),
        positions_by_class=MappingProxyType({value: 1 for value in classes}),
        positions_by_category=MappingProxyType({value: 1 for value in categories}),
        duplicate_count=0,
        warnings=(),
    )
    return DailyPortfolioSnapshot(
        reference_date=date(2026, 7, 30),
        generated_at=NOW,
        owners=(),
        institutions=institutions,
        currencies=currencies,
        institution_snapshots=(),
        consolidated=consolidated,
        status=DailyPortfolioStatus.READY,
        summary=DailyPortfolioSummary(1, 1, 2, 2, 0, 0, 0),
    )


def fact(identifier: str) -> ImportantFact:
    return ImportantFact(identifier, "HIGH", "MARKETS", identifier, "Description", "Source")


def facts(*items: tuple[str, tuple[str, ...]]) -> ImportantFactsResult:
    return ImportantFactsResult(
        important_facts=tuple(fact(identifier) for identifier, _ in items),
        relevance=tuple(
            FactRelevance(identifier, 100, bool(terms), terms)
            for identifier, terms in items
        ),
    )


def build(
    result: ImportantFactsResult, portfolio: DailyPortfolioSnapshot | None = None
) -> PortfolioImpactResult:
    return PortfolioImpactEngine(clock=lambda: NOW).build(portfolio or snapshot(), result)


def test_zero_facts_and_summary() -> None:
    result = build(ImportantFactsResult((), ()))
    assert result.impacts == ()
    assert result.summary.fact_count == result.summary.impact_count == 0
    assert result.summary.no_impact_count == 0


def test_no_impact_is_preserved_with_empty_dimensions() -> None:
    impact = build(facts(("global", ()))) .impacts[0]
    assert impact.fact_id == "global"
    assert impact.impact_level is ImpactLevel.NONE
    assert impact.impact_type is ImpactType.NONE
    assert impact.confidence == Decimal("0")
    assert impact.affected_assets == impact.affected_sectors == ()
    assert impact.affected_currencies == impact.affected_countries == ()
    assert impact.affected_themes == ()
    assert impact.reason == "No explicit structural match with the portfolio snapshot."


@pytest.mark.parametrize(
    ("terms", "level", "confidence"),
    [
        (("usd",), ImpactLevel.MODERATE, Decimal("0.85")),
        (("ubs",), ImpactLevel.HIGH, Decimal("0.95")),
        (("usd", "brl"), ImpactLevel.HIGH, Decimal("0.90")),
    ],
)
def test_direct_impacts(
    terms: tuple[str, ...], level: ImpactLevel, confidence: Decimal
) -> None:
    portfolio = snapshot(currencies=("USD", "BRL"))
    impact = build(facts(("direct", terms)), portfolio).impacts[0]
    assert impact.impact_type is ImpactType.DIRECT
    assert impact.impact_level is level
    assert impact.confidence == confidence


@pytest.mark.parametrize(
    ("terms", "level", "confidence"),
    [
        (("equities",), ImpactLevel.LOW, Decimal("0.50")),
        (("equities", "technology"), ImpactLevel.MODERATE, Decimal("0.65")),
    ],
)
def test_indirect_impacts(
    terms: tuple[str, ...], level: ImpactLevel, confidence: Decimal
) -> None:
    impact = build(facts(("indirect", terms))).impacts[0]
    assert impact.impact_type is ImpactType.INDIRECT
    assert impact.impact_level is level
    assert impact.confidence == confidence


def test_dimensions_are_deduplicated_sorted_and_official_values_preserved() -> None:
    portfolio = snapshot(
        institutions=("ubs", "Santander"),
        currencies=("usd", "BRL"),
        classes=("Equities", "Fixed Income"),
        categories=("Technology", "Banks"),
    )
    terms = ("USD", "brl", "usd", "SANTANDER", "equities", "fixed income", "banks")
    impact = build(facts(("dimensions", terms)), portfolio).impacts[0]
    assert impact.affected_institutions == ("Santander",)
    assert impact.affected_currencies == ("BRL", "usd")
    assert impact.affected_asset_classes == ("Equities", "Fixed Income")
    assert impact.affected_categories == ("Banks",)
    assert impact.affected_assets == impact.affected_sectors == ()
    assert impact.affected_countries == impact.affected_themes == ()


def test_impacts_are_one_per_fact_and_deterministically_ordered() -> None:
    result = build(facts(("z", ()), ("A", ("USD",)), ("a", ("UBS",))))
    assert tuple(item.fact_id for item in result.impacts) == ("A", "a", "z")
    assert len(result.impacts) == 3
    assert result.summary.fact_count == 3


def test_summary_counts_impacts_and_unique_required_dimensions() -> None:
    result = build(
        facts(("none", ()), ("currency-1", ("USD",)), ("currency-2", ("usd",)), ("class", ("Equities",)))
    )
    assert result.summary.impact_count == 3
    assert result.summary.direct_impact_count == 2
    assert result.summary.indirect_impact_count == 1
    assert result.summary.high_impact_count == 0
    assert result.summary.moderate_impact_count == 2
    assert result.summary.low_impact_count == 1
    assert result.summary.no_impact_count == 1
    assert result.summary.affected_currency_count == 1
    assert result.summary.affected_asset_count == 0
    assert result.summary.affected_sector_count == 0
    assert result.summary.affected_country_count == 0
    assert result.summary.affected_theme_count == 0


def test_reference_date_and_controlled_generated_at() -> None:
    result = build(facts(("none", ())))
    assert result.reference_date == date(2026, 7, 30)
    assert result.generated_at == NOW


def test_generated_at_is_normalized_to_utc_and_must_be_aware() -> None:
    assert PortfolioImpactEngine(clock=lambda: NOW).build(snapshot(), facts()).generated_at == NOW
    with pytest.raises(ValueError, match="timezone-aware"):
        PortfolioImpactEngine(clock=lambda: datetime(2026, 7, 30)).build(snapshot(), facts())


def test_contracts_are_shallowly_and_deeply_immutable() -> None:
    result = build(facts(("currency", ("USD",))))
    with pytest.raises(FrozenInstanceError):
        result.reference_date = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.impacts[0].reason = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.impacts[0].affected_currencies[0] = "BRL"  # type: ignore[index]


def test_invalid_confidence_and_runtime_types_are_rejected() -> None:
    base = build(facts(("none", ()))).impacts[0]
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(base, confidence=Decimal("1.01"))
    with pytest.raises(TypeError, match="Decimal"):
        replace(base, confidence=cast(Decimal, 0.5))
    with pytest.raises(TypeError, match="tuples"):
        replace(base, affected_assets=cast(tuple[str, ...], ["x"]))
    with pytest.raises(ValueError, match="unique"):
        replace(base, affected_assets=("z", "A", "A"))
    with pytest.raises(TypeError, match="DailyPortfolioSnapshot"):
        PortfolioImpactEngine().build(cast(DailyPortfolioSnapshot, object()), facts())
    with pytest.raises(TypeError, match="ImportantFactsResult"):
        PortfolioImpactEngine().build(snapshot(), cast(ImportantFactsResult, object()))


def test_input_objects_and_nested_collections_are_preserved() -> None:
    portfolio = snapshot()
    facts_result = facts(("currency", ("USD",)))
    portfolio_before = repr(portfolio)
    facts_before = repr(facts_result)
    build(facts_result, portfolio)
    assert repr(portfolio) == portfolio_before
    assert repr(facts_result) == facts_before
    assert facts_result.relevance[0].matched_portfolio_terms == ("USD",)


def test_equivalent_input_orders_produce_same_result() -> None:
    portfolio_a = snapshot(currencies=("USD", "BRL"), classes=("Equities", "Bonds"))
    portfolio_b = snapshot(currencies=("BRL", "USD"), classes=("Bonds", "Equities"))
    facts_a = facts(("z", ("USD", "BRL")), ("a", ("Equities", "Bonds")))
    facts_b = facts(("a", ("Bonds", "Equities")), ("z", ("BRL", "USD")))
    assert build(facts_a, portfolio_a) == build(facts_b, portfolio_b)


def test_absent_dimensions_are_not_inferred_from_fact_text() -> None:
    descriptive = ImportantFact(
        "text", "HIGH", "CORPORATE", "NVDA and Brazil", "Technology ETF in Brazil", "Source"
    )
    result = ImportantFactsResult((descriptive,), (FactRelevance("text", 90, False, ()),))
    impact = build(result).impacts[0]
    assert impact.impact_type is ImpactType.NONE
    assert impact.affected_assets == impact.affected_countries == impact.affected_themes == ()


def test_important_facts_and_daily_brief_compatibility() -> None:
    candidate = FactCandidate(
        id="currency",
        title="Explicit currency fact",
        description="Objective description",
        source="Source",
        published_at=NOW,
        importance=FactImportance.HIGH,
        category=FactCategory.MARKETS,
        related_currencies=(" usd ",),
    )
    facts_result = ImportantFactsEngine(clock=lambda: NOW).select((candidate,), snapshot())
    impact_result = build(facts_result)
    brief = DailyBriefEngine(clock=lambda: NOW).build(
        snapshot(), important_facts=facts_result.important_facts
    )
    assert impact_result.impacts[0].affected_currencies == ("USD",)
    assert brief.important_facts == facts_result.important_facts


def test_result_rejects_mutable_or_invalid_nested_values() -> None:
    result = build(facts(("none", ())))
    with pytest.raises(TypeError, match="tuple"):
        replace(result, impacts=cast(tuple[PortfolioImpact, ...], []))
    with pytest.raises(ValueError, match="timezone"):
        replace(result, generated_at=datetime(2026, 7, 30))


@pytest.mark.parametrize(
    ("path", "institution", "owner"),
    (
        (
            Path("frontend/test/fixtures/UBS_Holdings_27_07_2026.csv"),
            "UBS",
            PortfolioOwner.JOLIKA,
        ),
        (
            Path("frontend/test/fixtures/your-positions-4005106-38.xlsx"),
            "Santander",
            PortfolioOwner.JOLIKA,
        ),
        (
            Path("tests/fixtures/bradesco_private_fixture_oficial_marco_8_2b.txt"),
            "Bradesco",
            PortfolioOwner.NEI,
        ),
    ),
)
def test_official_connector_to_portfolio_impact_flow(
    path: Path, institution: str, owner: PortfolioOwner
) -> None:
    connector = tuple(item for item in registry.active() if item.recognize(path))[0]
    positions = connector.load_positions(path)
    original_positions = repr(positions)
    portfolio = DailyPortfolioSnapshotBuilder().build(
        positions, reference_date=date(2026, 7, 30)
    )
    candidate = FactCandidate(
        id=f"{institution}-fact",
        title=f"Explicit {institution} fact",
        description="Objective structural fact",
        source="Structured source",
        published_at=NOW,
        importance=FactImportance.HIGH,
        category=FactCategory.CORPORATE,
        related_institutions=(institution,),
    )
    selected = ImportantFactsEngine(clock=lambda: NOW).select((candidate,), portfolio)
    result = PortfolioImpactEngine(clock=lambda: NOW).build(portfolio, selected)

    assert portfolio.owners == (owner,)
    assert portfolio.institutions == (institution,)
    assert result.impacts[0].affected_institutions == (institution,)
    assert result.impacts[0].impact_type is ImpactType.DIRECT
    assert all(
        isinstance(value, Decimal)
        for value in portfolio.consolidated.gross_value_by_currency.values()
    )
    assert repr(positions) == original_positions
    assert result == PortfolioImpactEngine(clock=lambda: NOW).build(portfolio, selected)


def test_all_official_connectors_remain_separated_end_to_end() -> None:
    paths = (
        Path("frontend/test/fixtures/UBS_Holdings_27_07_2026.csv"),
        Path("frontend/test/fixtures/your-positions-4005106-38.xlsx"),
        Path("tests/fixtures/bradesco_private_fixture_oficial_marco_8_2b.txt"),
    )
    positions = tuple(
        position
        for path in paths
        for connector in registry.active()
        if connector.recognize(path)
        for position in connector.load_positions(path)
    )
    positions_before = repr(positions)
    portfolio = DailyPortfolioSnapshotBuilder().build(
        positions, reference_date=date(2026, 7, 30)
    )
    candidates = tuple(
        FactCandidate(
            id=institution.casefold(),
            title=f"Explicit {institution} fact",
            description="Objective structural fact",
            source="Structured source",
            published_at=NOW,
            importance=FactImportance.HIGH,
            category=FactCategory.CORPORATE,
            related_institutions=(institution,),
        )
        for institution in ("UBS", "Santander", "Bradesco")
    )
    selected = ImportantFactsEngine(clock=lambda: NOW).select(candidates, portfolio)
    selected_before = repr(selected)
    result = PortfolioImpactEngine(clock=lambda: NOW).build(portfolio, selected)

    assert portfolio.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert portfolio.institutions == ("Bradesco", "Santander", "UBS")
    assert set(portfolio.consolidated.positions_by_owner) == {"JOLIKA", "NEI"}
    assert portfolio.currencies == tuple(
        sorted(portfolio.consolidated.gross_value_by_currency)
    )
    assert all(
        isinstance(value, Decimal)
        for value in portfolio.consolidated.gross_value_by_currency.values()
    )
    assert {item.fact_id for item in result.impacts} == {
        "bradesco",
        "santander",
        "ubs",
    }
    assert all(item.impact_type is ImpactType.DIRECT for item in result.impacts)
    assert repr(positions) == positions_before
    assert repr(selected) == selected_before
    assert result == PortfolioImpactEngine(clock=lambda: NOW).build(portfolio, selected)
