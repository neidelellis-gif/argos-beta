from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from backend.connectors import registry
from backend.daily_brief import (
    AnalysisItem,
    AnalysisType,
    DailyBriefEngine,
    DailyBriefStatus,
    DailyPriority,
    DailyPriorityLevel,
    ImportantFact,
    MarketAgendaItem,
)
from backend.daily_portfolio_snapshot import (
    DailyPortfolioSnapshot,
    DailyPortfolioSnapshotBuilder,
)
from backend.import_validation import ImportValidationStatus
from backend.models import PortfolioOwner, PortfolioPosition


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def position(
    institution: str = "UBS",
    identifier: str = "AAA",
    *,
    owner: PortfolioOwner = PortfolioOwner.JOLIKA,
    currency: str | None = "USD",
    asset_class: str | None = "Equity",
    asset_subclass: str | None = "Stock",
) -> PortfolioPosition:
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=f"{institution}-1",
        asset_class=asset_class,
        asset_subclass=asset_subclass,
        asset_name=f"Asset {identifier}",
        identifier=identifier,
        identifier_type="Ticker",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal("100"),
        currency=currency,
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )


def brief_for(positions: list[PortfolioPosition] | None = None):
    snapshot = DailyPortfolioSnapshotBuilder().build(
        positions or [], reference_date=date(2026, 7, 30)
    )
    return DailyBriefEngine(clock=lambda: NOW).build(snapshot)


def fact(number: int, priority: str = "MEDIUM") -> ImportantFact:
    return ImportantFact(
        id=str(number),
        priority=priority,
        category="Macro",
        title=f"Fact {number}",
        description=f"Description {number}",
        source="Structured source",
    )


def priority(level: DailyPriorityLevel, title: str) -> DailyPriority:
    return DailyPriority(level, title, f"Description {title}", f"Reason {title}")


def analysis(kind: AnalysisType, title: str) -> AnalysisItem:
    return AnalysisItem(title, f"Description {title}", kind, "Structured source")


@pytest.mark.parametrize(
    ("positions", "expected"),
    (
        ([], DailyBriefStatus.EMPTY),
        ([position()], DailyBriefStatus.READY),
        ([position(asset_subclass=None)], DailyBriefStatus.READY_WITH_WARNINGS),
        ([position(currency=None)], DailyBriefStatus.BLOCKED),
    ),
)
def test_maps_every_snapshot_status_directly(positions, expected):
    assert brief_for(positions).status is expected


def test_derives_identification_and_complete_operational_health_from_snapshot():
    positions = [
        position("UBS", "A", currency="USD"),
        position("Santander", "B", currency="BRL"),
    ]
    snapshot = DailyPortfolioSnapshotBuilder().build(
        positions, reference_date=date(2026, 7, 29)
    )

    brief = DailyBriefEngine(clock=lambda: NOW).build(snapshot)

    assert brief.reference_date == date(2026, 7, 29)
    assert brief.generated_at == NOW
    assert brief.owners == (PortfolioOwner.JOLIKA,)
    assert brief.institutions == ("Santander", "UBS")
    assert brief.currencies == ("BRL", "USD")
    assert brief.portfolio_health.status is DailyBriefStatus.READY
    assert brief.portfolio_health.validation_status == (
        ImportValidationStatus.APPROVED,
        ImportValidationStatus.APPROVED,
    )
    assert brief.portfolio_health.institution_count == 2
    assert brief.portfolio_health.owner_count == 1
    assert brief.portfolio_health.position_count == 2
    assert brief.portfolio_health.asset_count == 2
    assert brief.portfolio_health.warning_count == 0
    assert brief.portfolio_health.error_count == 0
    assert brief.portfolio_health.duplicate_count == 0


def test_all_optional_content_is_empty_by_default():
    brief = brief_for()

    assert brief.important_facts == ()
    assert brief.priorities == ()
    assert brief.analyses == ()
    assert brief.market_agenda == ()


def test_facts_are_deterministically_sorted_and_limited_to_five():
    snapshot = DailyPortfolioSnapshotBuilder().build([])
    items = [fact(number) for number in (7, 2, 5, 1, 6, 3, 4)]

    brief = DailyBriefEngine(clock=lambda: NOW).build(
        snapshot, important_facts=reversed(items)
    )

    assert tuple(item.id for item in brief.important_facts) == ("1", "2", "3", "4", "5")
    assert len(DailyBriefEngine(clock=lambda: NOW).build(
        snapshot, important_facts=items[:5]
    ).important_facts) == 5


def test_fact_priority_participates_in_stable_ordering():
    snapshot = DailyPortfolioSnapshotBuilder().build([])

    brief = DailyBriefEngine(clock=lambda: NOW).build(
        snapshot, important_facts=(fact(1, "LOW"), fact(2, "HIGH"))
    )

    assert tuple(item.priority for item in brief.important_facts) == ("HIGH", "LOW")


def test_priorities_keep_one_deterministic_item_per_level_in_required_order():
    snapshot = DailyPortfolioSnapshotBuilder().build([])
    items = (
        priority(DailyPriorityLevel.LOW, "Low"),
        priority(DailyPriorityLevel.HIGH, "Zulu"),
        priority(DailyPriorityLevel.MODERATE, "Moderate"),
        priority(DailyPriorityLevel.HIGH, "Alpha"),
    )

    forward = DailyBriefEngine(clock=lambda: NOW).build(snapshot, priorities=items)
    reverse = DailyBriefEngine(clock=lambda: NOW).build(
        snapshot, priorities=reversed(items)
    )

    assert forward.priorities == reverse.priorities
    assert tuple(item.level for item in forward.priorities) == (
        DailyPriorityLevel.HIGH,
        DailyPriorityLevel.MODERATE,
        DailyPriorityLevel.LOW,
    )
    assert forward.priorities[0].title == "Alpha"


@pytest.mark.parametrize("count", (0, 1, 2, 3))
def test_analyses_are_limited_to_two_and_ordered_by_type(count):
    snapshot = DailyPortfolioSnapshotBuilder().build([])
    items = (
        analysis(AnalysisType.DECIDE, "Decide"),
        analysis(AnalysisType.ANALYZE, "Zulu"),
        analysis(AnalysisType.ANALYZE, "Alpha"),
    )[:count]

    brief = DailyBriefEngine(clock=lambda: NOW).build(snapshot, analyses=items)

    assert len(brief.analyses) == min(count, 2)
    assert tuple(item.type for item in brief.analyses) == tuple(
        sorted((item.type for item in items), key=lambda item: item.value)[:2]
    )


def test_market_agenda_is_sorted_by_date_and_deterministic_tiebreakers():
    snapshot = DailyPortfolioSnapshotBuilder().build([])
    items = (
        MarketAgendaItem(date(2026, 8, 1), "Later", "Macro", "HIGH", "Source"),
        MarketAgendaItem(date(2026, 7, 31), "Zulu", "Macro", "LOW", "Source"),
        MarketAgendaItem(date(2026, 7, 31), "Alpha", "Macro", "LOW", "Source"),
    )

    brief = DailyBriefEngine(clock=lambda: NOW).build(
        snapshot, market_agenda=reversed(items)
    )

    assert tuple(item.title for item in brief.market_agenda) == ("Alpha", "Zulu", "Later")


def test_contracts_are_deeply_immutable_and_inputs_are_preserved():
    snapshot = DailyPortfolioSnapshotBuilder().build([position()])
    original_snapshot = replace(snapshot)
    facts = [fact(2), fact(1)]
    original_facts = list(facts)
    brief = DailyBriefEngine(clock=lambda: NOW).build(snapshot, important_facts=facts)

    with pytest.raises(FrozenInstanceError):
        setattr(brief, "status", DailyBriefStatus.BLOCKED)
    with pytest.raises(FrozenInstanceError):
        setattr(brief.portfolio_health, "error_count", 99)
    with pytest.raises(FrozenInstanceError):
        setattr(brief.important_facts[0], "title", "Changed")

    assert snapshot == original_snapshot
    assert facts == original_facts


def test_same_inputs_are_deterministic_with_an_injected_clock():
    snapshot = DailyPortfolioSnapshotBuilder().build([position()])
    engine = DailyBriefEngine(clock=lambda: NOW)

    assert engine.build(snapshot, important_facts=(fact(2), fact(1))) == engine.build(
        snapshot, important_facts=(fact(1), fact(2))
    )


def test_preserves_owner_institution_currency_and_decimal_boundaries_end_to_end():
    positions = [
        position("UBS", "UBS", owner=PortfolioOwner.JOLIKA, currency="USD"),
        position("Santander", "SAN", owner=PortfolioOwner.JOLIKA, currency="BRL"),
        position("Bradesco", "BRA", owner=PortfolioOwner.NEI, currency="BRL"),
    ]
    original = list(positions)
    snapshot = DailyPortfolioSnapshotBuilder().build(positions)

    brief = DailyBriefEngine(clock=lambda: NOW).build(snapshot)

    assert brief.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert brief.institutions == ("Bradesco", "Santander", "UBS")
    assert brief.currencies == ("BRL", "USD")
    assert snapshot.consolidated.gross_value_by_currency == {
        "BRL": Decimal("200"),
        "USD": Decimal("100"),
    }
    assert positions == original
    assert brief.important_facts == brief.priorities == brief.analyses == ()


@pytest.mark.parametrize(
    ("path", "institution", "owner"),
    (
        (
            "frontend/test/fixtures/UBS_Holdings_27_07_2026.csv",
            "UBS",
            PortfolioOwner.JOLIKA,
        ),
        (
            "frontend/test/fixtures/your-positions-4005106-38.xlsx",
            "Santander",
            PortfolioOwner.JOLIKA,
        ),
        (
            "tests/fixtures/bradesco_private_fixture_oficial_marco_8_2b.txt",
            "Bradesco",
            PortfolioOwner.NEI,
        ),
    ),
)
def test_official_connector_to_brief_flow(path, institution, owner):
    connectors = tuple(
        connector
        for connector in registry.active()
        if connector.recognize(path)
    )
    assert len(connectors) == 1

    positions = connectors[0].load_positions(path)
    snapshot = DailyPortfolioSnapshotBuilder().build(positions)
    brief = DailyBriefEngine(clock=lambda: NOW).build(snapshot)

    assert brief.institutions == (institution,)
    assert brief.owners == (owner,)
    assert all(isinstance(value, Decimal) for value in snapshot.consolidated.gross_value_by_currency.values())


def test_all_official_institutions_flow_together_without_crossing_boundaries():
    paths: tuple[Path, ...] = (
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

    snapshot = DailyPortfolioSnapshotBuilder().build(positions)
    brief = DailyBriefEngine(clock=lambda: NOW).build(snapshot)

    assert brief.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert brief.institutions == ("Bradesco", "Santander", "UBS")
    assert brief.currencies == tuple(sorted(snapshot.consolidated.gross_value_by_currency))
    assert set(snapshot.consolidated.positions_by_owner) == {"JOLIKA", "NEI"}
    assert all(isinstance(value, Decimal) for value in snapshot.consolidated.gross_value_by_currency.values())


@pytest.mark.parametrize(
    ("keyword", "bad_value", "message"),
    (
        ("important_facts", (object(),), "important_facts"),
        ("priorities", (object(),), "priorities"),
        ("analyses", (object(),), "analyses"),
        ("market_agenda", (object(),), "market_agenda"),
    ),
)
def test_rejects_invalid_structured_content(keyword, bad_value, message):
    snapshot = DailyPortfolioSnapshotBuilder().build([])

    with pytest.raises(TypeError, match=message):
        DailyBriefEngine(clock=lambda: NOW).build(snapshot, **{keyword: bad_value})


def test_rejects_any_input_other_than_the_official_snapshot():
    with pytest.raises(TypeError, match="DailyPortfolioSnapshot"):
        DailyBriefEngine(clock=lambda: NOW).build(
            cast("DailyPortfolioSnapshot", object())
        )
