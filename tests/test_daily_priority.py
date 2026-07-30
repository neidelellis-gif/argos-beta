from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from backend.connectors import registry
from backend.daily_brief import DailyBriefEngine, DailyPriorityLevel, ImportantFact
from backend.daily_portfolio_snapshot import (
    ConsolidatedPortfolioSnapshot,
    DailyPortfolioSnapshot,
    DailyPortfolioSnapshotBuilder,
    DailyPortfolioStatus,
    DailyPortfolioSummary,
)
from backend.daily_priority import (
    AffectedDimension,
    AffectedDimensionType,
    DailyPriorityAction,
    DailyPriorityEngine,
)
from backend.important_facts import (
    FactCandidate,
    FactCategory,
    FactImportance,
    FactRelevance,
    ImportantFactsEngine,
    ImportantFactsResult,
)
from backend.models import PortfolioOwner
from backend.portfolio_impact import (
    ImpactLevel,
    ImpactType,
    PortfolioImpact,
    PortfolioImpactEngine,
    PortfolioImpactResult,
    PortfolioImpactSummary,
)


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def snapshot() -> DailyPortfolioSnapshot:
    return DailyPortfolioSnapshot(
        reference_date=date(2026, 7, 30), generated_at=NOW, owners=(),
        institutions=("Santander", "UBS", "Bradesco"), currencies=("BRL", "USD"),
        institution_snapshots=(),
        consolidated=ConsolidatedPortfolioSnapshot(
            0, 0, MappingProxyType({"BRL": Decimal("1"), "USD": Decimal("1")}),
            MappingProxyType({"JOLIKA": 2, "NEI": 1}),
            MappingProxyType({"Santander": 1, "UBS": 1, "Bradesco": 1}),
            MappingProxyType({"Equities": 1}), MappingProxyType({"Technology": 1}),
            0, (),
        ),
        status=DailyPortfolioStatus.READY,
        summary=DailyPortfolioSummary(3, 2, 0, 0, 0, 0, 0),
    )


def fact(identifier: str, priority: str = "HIGH") -> ImportantFact:
    return ImportantFact(identifier, priority, "MARKETS", f"Title {identifier}", "Text", "Source")


def facts(*identifiers: str) -> ImportantFactsResult:
    return ImportantFactsResult(
        tuple(fact(identifier) for identifier in identifiers),
        tuple(FactRelevance(identifier, 1, True, ()) for identifier in identifiers),
    )


def impact(
    identifier: str, level: ImpactLevel = ImpactLevel.HIGH,
    kind: ImpactType = ImpactType.DIRECT, confidence: Decimal = Decimal("0.95"),
    *, institutions: tuple[str, ...] = ("UBS",), currencies: tuple[str, ...] = (),
    classes: tuple[str, ...] = (), categories: tuple[str, ...] = (),
) -> PortfolioImpact:
    return PortfolioImpact(
        identifier, level, kind, (), (), currencies, (), (), "Existing impact.", confidence,
        affected_institutions=institutions,
        affected_asset_classes=classes, affected_categories=categories,
    )


def impacts(*items: PortfolioImpact) -> PortfolioImpactResult:
    return PortfolioImpactResult(
        date(2026, 7, 30), NOW, items,
        PortfolioImpactSummary(len(items), len(items), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    )


def build(fact_result: ImportantFactsResult, *items: PortfolioImpact):
    return DailyPriorityEngine(clock=lambda: NOW).build(snapshot(), fact_result, impacts(*items))


def test_empty_facts_and_impacts_is_valid() -> None:
    result = build(facts())
    assert result.priorities == ()
    assert result.reference_date == date(2026, 7, 30)
    assert result.generated_at == NOW
    assert result.summary.fact_count == result.summary.impact_count == 0


def test_zero_impacts_and_fact_without_priority() -> None:
    result = build(facts("a"))
    assert result.priorities == ()
    assert result.summary.fact_count == 1
    assert result.summary.impact_count == 0


def test_none_and_structurally_empty_impacts_are_excluded() -> None:
    none = impact("none", ImpactLevel.NONE, ImpactType.NONE, Decimal("0"), institutions=())
    empty = impact("empty", institutions=())
    result = build(facts("none", "empty"), none, empty)
    assert result.priorities == ()
    assert result.summary.excluded_no_impact_count == 2


@pytest.mark.parametrize(
    ("level", "kind", "confidence", "dimensions", "expected_level", "expected_action"),
    [
        (ImpactLevel.HIGH, ImpactType.DIRECT, "0.95", 1, DailyPriorityLevel.HIGH, DailyPriorityAction.DECIDE),
        (ImpactLevel.HIGH, ImpactType.DIRECT, "0.90", 1, DailyPriorityLevel.HIGH, DailyPriorityAction.DECIDE),
        (ImpactLevel.HIGH, ImpactType.DIRECT, "0.89", 1, DailyPriorityLevel.MODERATE, DailyPriorityAction.ANALYZE),
        (ImpactLevel.HIGH, ImpactType.INDIRECT, "0.95", 1, DailyPriorityLevel.MODERATE, DailyPriorityAction.ANALYZE),
        (ImpactLevel.MODERATE, ImpactType.DIRECT, "0.50", 1, DailyPriorityLevel.MODERATE, DailyPriorityAction.ANALYZE),
        (ImpactLevel.MODERATE, ImpactType.INDIRECT, "0.65", 1, DailyPriorityLevel.MODERATE, DailyPriorityAction.ANALYZE),
        (ImpactLevel.LOW, ImpactType.INDIRECT, "0.50", 1, DailyPriorityLevel.LOW, DailyPriorityAction.ANALYZE),
        (ImpactLevel.LOW, ImpactType.INDIRECT, "0.50", 2, DailyPriorityLevel.MODERATE, DailyPriorityAction.ANALYZE),
    ],
)
def test_official_classification_matrix(
    level: ImpactLevel, kind: ImpactType, confidence: str, dimensions: int,
    expected_level: DailyPriorityLevel, expected_action: DailyPriorityAction,
) -> None:
    item = impact(
        "a", level, kind, Decimal(confidence),
        currencies=("USD",) if dimensions == 2 else (),
    )
    priority = build(facts("a"), item).priorities[0]
    assert priority.level is expected_level
    assert priority.action is expected_action


def test_limit_ordering_tiebreakers_and_summary() -> None:
    items = (
        impact("low", ImpactLevel.LOW, ImpactType.INDIRECT, Decimal("0.50")),
        impact("moderate", ImpactLevel.MODERATE, ImpactType.INDIRECT, Decimal("0.65")),
        impact("high-z", confidence=Decimal("0.95")),
        impact("high-a", confidence=Decimal("0.95")),
        impact("high-less", confidence=Decimal("0.90")),
    )
    result = build(facts(*(item.fact_id for item in items)), *items)
    assert tuple(item.fact_id for item in result.priorities) == ("high-a", "high-z", "high-less")
    assert result.summary.eligible_priority_count == 5
    assert result.summary.selected_priority_count == 3
    assert result.summary.excluded_by_limit_count == 2
    assert result.summary.high_priority_count == result.summary.decide_count == 3
    assert result.summary.moderate_priority_count == result.summary.low_priority_count == 0


def test_direct_and_impact_level_precede_confidence_within_priority_level() -> None:
    direct = impact("direct", ImpactLevel.MODERATE, ImpactType.DIRECT, Decimal("0.50"))
    indirect_high = impact("indirect-high", ImpactLevel.HIGH, ImpactType.INDIRECT, Decimal("0.99"))
    indirect_moderate = impact("indirect-moderate", ImpactLevel.MODERATE, ImpactType.INDIRECT, Decimal("0.99"))
    result = build(facts("indirect-moderate", "indirect-high", "direct"), indirect_moderate, indirect_high, direct)
    assert tuple(item.fact_id for item in result.priorities) == ("direct", "indirect-high", "indirect-moderate")


def test_importance_then_fact_id_are_final_tiebreakers() -> None:
    result_facts = ImportantFactsResult((fact("z", "LOW"), fact("b"), fact("a")), ())
    result = build(result_facts, impact("z"), impact("b"), impact("a"))
    assert tuple(item.fact_id for item in result.priorities) == ("a", "b", "z")


def test_input_and_dimension_orders_are_deterministic() -> None:
    one = impact("a", institutions=("UBS",), currencies=("BRL", "USD"), classes=("Equities",), categories=("Technology",))
    two = impact("b", institutions=("Santander",))
    first = build(facts("b", "a"), two, one)
    second = build(facts("a", "b"), one, two)
    assert first == second
    dimensions = first.priorities[0].affected_dimensions
    assert dimensions == (
        AffectedDimension(AffectedDimensionType.INSTITUTION, "UBS"),
        AffectedDimension(AffectedDimensionType.CURRENCY, "BRL"),
        AffectedDimension(AffectedDimensionType.CURRENCY, "USD"),
        AffectedDimension(AffectedDimensionType.ASSET_CLASS, "Equities"),
        AffectedDimension(AffectedDimensionType.CATEGORY, "Technology"),
    )


def test_identity_title_reason_and_official_values_are_preserved() -> None:
    original = ImportantFact("id", "HIGH", "MARKETS", "  Original title  ", "buy sell forecast", "Source")
    item = impact("id", institutions=("Banco Ágil",), currencies=("USD",))
    priority = build(ImportantFactsResult((original,), ()), item).priorities[0]
    assert priority.priority_id == "priority:id"
    assert priority.fact_id == "id"
    assert priority.title == "  Original title  "
    assert "Banco Ágil" in priority.reason and "USD" in priority.reason
    assert all(word not in priority.reason.casefold() for word in ("comprar", "vender", "preço-alvo", "previsão"))
    assert priority.confidence is item.confidence


def test_orphan_duplicate_and_reference_date_inconsistencies_are_rejected() -> None:
    with pytest.raises(ValueError, match="existing fact_id"):
        build(facts("a"), impact("orphan"))
    with pytest.raises(ValueError, match="impact fact_ids"):
        build(facts("a"), impact("a"), impact("a"))
    duplicate_facts = ImportantFactsResult((fact("A"), fact("a")), ())
    with pytest.raises(ValueError, match="fact ids"):
        build(duplicate_facts)
    mismatched = replace(impacts(impact("a")), reference_date=date(2026, 7, 29))
    with pytest.raises(ValueError, match="reference_date"):
        DailyPriorityEngine().build(snapshot(), facts("a"), mismatched)


def test_runtime_types_confidence_and_clock_are_validated() -> None:
    base = impact("a")
    with pytest.raises(TypeError, match="Decimal"):
        replace(base, confidence=cast(Decimal, 0.5))
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(base, confidence=Decimal("-0.01"))
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(base, confidence=Decimal("1.01"))
    assert replace(base, confidence=Decimal("0")).confidence == Decimal("0")
    assert replace(base, confidence=Decimal("1")).confidence == Decimal("1")
    with pytest.raises(ValueError, match="timezone-aware"):
        DailyPriorityEngine(clock=lambda: datetime(2026, 7, 30)).build(snapshot(), facts(), impacts())
    offset = timezone(timedelta(hours=-3))
    result = DailyPriorityEngine(clock=lambda: NOW.astimezone(offset)).build(snapshot(), facts(), impacts())
    assert result.generated_at == NOW and result.generated_at.tzinfo is timezone.utc
    with pytest.raises(TypeError, match="DailyPortfolioSnapshot"):
        DailyPriorityEngine().build(cast(DailyPortfolioSnapshot, object()), facts(), impacts())


def test_contracts_and_inputs_are_deeply_immutable_and_preserved() -> None:
    portfolio = snapshot()
    fact_result = facts("a")
    impact_result = impacts(impact("a"))
    before = (repr(portfolio), repr(fact_result), repr(impact_result))
    result = DailyPriorityEngine(clock=lambda: NOW).build(portfolio, fact_result, impact_result)
    assert (repr(portfolio), repr(fact_result), repr(impact_result)) == before
    with pytest.raises(FrozenInstanceError):
        result.reference_date = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.priorities[0].reason = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.priorities[0].affected_dimensions[0] = AffectedDimension(AffectedDimensionType.CURRENCY, "BRL")  # type: ignore[index]


def test_official_engine_compatibility_and_no_monetary_output() -> None:
    fact_result = facts("ubs", "santander", "bradesco", "global")
    relevance = ImportantFactsResult(
        fact_result.important_facts,
        (
            FactRelevance("ubs", 1, True, ("UBS",)),
            FactRelevance("santander", 1, True, ("Santander",)),
            FactRelevance("bradesco", 1, True, ("Bradesco",)),
            FactRelevance("global", 1, False, ()),
        ),
    )
    impact_result = PortfolioImpactEngine(clock=lambda: NOW).build(snapshot(), relevance)
    result = DailyPriorityEngine(clock=lambda: NOW).build(snapshot(), relevance, impact_result)
    assert len(result.priorities) == 3
    assert {item.fact_id for item in result.priorities} == {"ubs", "santander", "bradesco"}
    assert all(item.action is DailyPriorityAction.DECIDE for item in result.priorities)
    assert "global" not in {item.fact_id for item in result.priorities}
    assert not hasattr(result.summary, "gross_value")
    DailyBriefEngine(clock=lambda: NOW).build(snapshot(), important_facts=relevance.important_facts)


@pytest.mark.parametrize(
    ("path", "institution", "owner"),
    (
        (Path("frontend/test/fixtures/UBS_Holdings_27_07_2026.csv"), "UBS", PortfolioOwner.JOLIKA),
        (Path("frontend/test/fixtures/your-positions-4005106-38.xlsx"), "Santander", PortfolioOwner.JOLIKA),
        (Path("tests/fixtures/bradesco_private_fixture_oficial_marco_8_2b.txt"), "Bradesco", PortfolioOwner.NEI),
    ),
)
def test_official_connector_to_daily_priority_flow(
    path: Path, institution: str, owner: PortfolioOwner,
) -> None:
    connector = tuple(item for item in registry.active() if item.recognize(path))[0]
    positions = connector.load_positions(path)
    before = repr(positions)
    portfolio = DailyPortfolioSnapshotBuilder().build(positions, date(2026, 7, 30))
    candidate = FactCandidate(
        f"{institution}-fact", f"Explicit {institution} fact", "Objective fact",
        "Structured source", NOW, FactImportance.HIGH, FactCategory.CORPORATE,
        related_institutions=(institution,),
    )
    selected = ImportantFactsEngine(clock=lambda: NOW).build((candidate,), portfolio)
    impact_result = PortfolioImpactEngine(clock=lambda: NOW).build(portfolio, selected)
    result = DailyPriorityEngine(clock=lambda: NOW).build(portfolio, selected, impact_result)
    assert portfolio.owners == (owner,)
    assert portfolio.institutions == (institution,)
    assert result.priorities[0].fact_id == f"{institution}-fact"
    assert result.priorities[0].action is DailyPriorityAction.DECIDE
    assert repr(positions) == before
    assert result == DailyPriorityEngine(clock=lambda: NOW).build(portfolio, selected, impact_result)


def test_all_official_connectors_to_daily_priority_remain_separated() -> None:
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
    before = repr(positions)
    portfolio = DailyPortfolioSnapshotBuilder().build(positions, date(2026, 7, 30))
    candidates = tuple(
        FactCandidate(
            institution.casefold(), f"Explicit {institution} fact", "Objective fact",
            "Structured source", NOW, FactImportance.HIGH, FactCategory.CORPORATE,
            related_institutions=(institution,),
        )
        for institution in ("UBS", "Santander", "Bradesco")
    )
    selected = ImportantFactsEngine(clock=lambda: NOW).build(candidates, portfolio)
    impact_result = PortfolioImpactEngine(clock=lambda: NOW).build(portfolio, selected)
    result = DailyPriorityEngine(clock=lambda: NOW).build(portfolio, selected, impact_result)
    assert portfolio.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert portfolio.institutions == ("Bradesco", "Santander", "UBS")
    assert portfolio.currencies == tuple(sorted(portfolio.consolidated.gross_value_by_currency))
    assert all(isinstance(value, Decimal) for value in portfolio.consolidated.gross_value_by_currency.values())
    assert {item.fact_id for item in result.priorities} == {"ubs", "santander", "bradesco"}
    assert len(result.priorities) == 3
    assert all(item.action is DailyPriorityAction.DECIDE for item in result.priorities)
    assert repr(positions) == before
