from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from backend.daily_brief import ImportantFact
from backend.daily_portfolio_snapshot import (
    DailyPortfolioSnapshot,
    DailyPortfolioSnapshotBuilder,
)
from backend.important_facts import (
    FactCandidate,
    FactCategory,
    FactImportance,
    ImportantFactsEngine,
)
from backend.models import PortfolioOwner, PortfolioPosition


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def candidate(
    identifier: str,
    *,
    importance: FactImportance = FactImportance.MEDIUM,
    hours_old: int = 1,
    title: str | None = None,
    currencies: tuple[str, ...] = (),
) -> FactCandidate:
    return FactCandidate(
        id=identifier,
        title=title or f"Fact {identifier}",
        description=f"Description {identifier}",
        source="Structured source",
        published_at=NOW - timedelta(hours=hours_old),
        importance=importance,
        category=FactCategory.MARKETS,
        related_currencies=currencies,
    )


def snapshot():
    position = PortfolioPosition(
        institution="UBS", owner=PortfolioOwner.JOLIKA, account="1",
        asset_class="Equity", asset_subclass="Stock", asset_name="Asset",
        identifier="AAA", identifier_type="Ticker", quantity=Decimal("1"),
        unit_price=Decimal("1"), market_value=Decimal("1"), currency="USD",
        portfolio_weight=None, reference_date=None, source_file="UBS.csv",
    )
    return DailyPortfolioSnapshotBuilder().build([position])


def test_selects_at_most_five_and_is_independent_of_input_order():
    items = tuple(candidate(str(number)) for number in range(7))
    engine = ImportantFactsEngine(clock=lambda: NOW)

    forward = engine.select(items, snapshot())
    reverse = engine.select(reversed(items), snapshot())

    assert forward == reverse
    assert len(forward.important_facts) == 5
    assert all(isinstance(item, ImportantFact) for item in forward.important_facts)


def test_portfolio_relation_boosts_but_does_not_exclude_important_global_fact():
    related = candidate("related", currencies=("usd",))
    global_critical = candidate("global", importance=FactImportance.CRITICAL)

    result = ImportantFactsEngine(clock=lambda: NOW).build(
        (related, global_critical), snapshot()
    )

    assert tuple(item.id for item in result.important_facts) == ("global", "related")
    assert result.relevance[0].portfolio_related is False
    assert result.relevance[1].matched_portfolio_terms == ("usd",)


def test_rejects_expired_future_and_incomplete_facts_without_inventing_content():
    expired = candidate("expired", hours_old=25)
    future = replace(candidate("future"), published_at=NOW + timedelta(seconds=1))
    incomplete = replace(candidate("incomplete"), source=" ")

    result = ImportantFactsEngine(clock=lambda: NOW).select(
        (expired, future, incomplete), snapshot()
    )

    assert result.important_facts == ()
    assert result.rejected_ids == ("expired", "future", "incomplete")


def test_removes_duplicate_ids_and_keeps_highest_ranked_version():
    low = candidate("same", importance=FactImportance.LOW, title="Old version")
    high = candidate("same", importance=FactImportance.HIGH, title="New version")

    result = ImportantFactsEngine(clock=lambda: NOW).select((low, high), snapshot())

    assert tuple(item.title for item in result.important_facts) == ("New version",)
    assert result.rejected_ids == ("same",)


def test_removes_equivalent_titles_even_when_sources_use_different_ids():
    first = candidate("one", title="Fed cuts rates")
    duplicate = candidate("two", title="FED: cuts rates!")

    result = ImportantFactsEngine(clock=lambda: NOW).select(
        (duplicate, first), snapshot()
    )

    assert len(result.important_facts) == 1
    assert result.rejected_ids == ("two",)


def test_contracts_and_inputs_are_immutable_and_snapshot_is_preserved():
    portfolio = snapshot()
    original = replace(portfolio)
    item = candidate("one")
    result = ImportantFactsEngine(clock=lambda: NOW).select((item,), portfolio)

    with pytest.raises(FrozenInstanceError):
        result.relevance[0].score = 0  # type: ignore[reportAttributeAccessIssue]
    with pytest.raises(FrozenInstanceError):
        item.title = "Changed"  # type: ignore[reportAttributeAccessIssue]
    assert portfolio == original


def test_rejects_wrong_contracts_and_naive_engine_clock():
    engine = ImportantFactsEngine(clock=lambda: NOW)
    with pytest.raises(TypeError, match="FactCandidate"):
        engine.select((cast(FactCandidate, object()),), snapshot())
    with pytest.raises(TypeError, match="DailyPortfolioSnapshot"):
        engine.select((), cast(DailyPortfolioSnapshot, object()))
    with pytest.raises(ValueError, match="timezone"):
        ImportantFactsEngine(clock=lambda: NOW.replace(tzinfo=None)).select((), snapshot())
    with pytest.raises(TypeError, match="tuples"):
        replace(candidate("mutable"), related_assets=["AAA"])
