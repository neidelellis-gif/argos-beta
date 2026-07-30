"""Tests for the isolated portfolio-aware daily facts engine."""

from datetime import date, datetime, timezone
from decimal import Decimal

from backend.daily_facts_engine import DailyFactsEngine
from backend.important_facts import FactCandidate, FactCategory, FactImportance
from backend.models import PortfolioOwner, PortfolioPosition


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def position(asset: str, sector: str = "Technology") -> PortfolioPosition:
    return PortfolioPosition(
        "UBS", PortfolioOwner.JOLIKA, "1", "Equities", sector, asset, asset,
        "TICKER", Decimal("1"), None, None, "USD", None, date(2026, 7, 30), "fixture",
    )


def event(
    identifier: str,
    asset: str = "ARGOS1",
    importance: FactImportance = FactImportance.MEDIUM,
    title: str | None = None,
    description: str = "A empresa divulgou seu resultado trimestral.",
) -> FactCandidate:
    return FactCandidate(
        identifier, title or f"Resultado de {identifier}", description, "Fonte", NOW,
        importance, FactCategory.CORPORATE, related_assets=(asset,),
    )


def test_empty_portfolio_and_irrelevant_context_return_no_facts() -> None:
    engine = DailyFactsEngine()
    assert engine.generate((), (event("one"),)) == []
    assert engine.generate((position("OTHER"),), (event("one"),)) == []


def test_one_asset_produces_complete_objective_fact() -> None:
    facts = DailyFactsEngine().generate((position("ARGOS1"),), (event("one"),))
    assert facts == [{
        "id": "one", "category": "CORPORATE", "priority": "MEDIUM",
        "title": "Resultado de one",
        "summary": "A empresa divulgou seu resultado trimestral.",
        "affected_assets": ["ARGOS1"],
    }]
    assert set(facts[0]) == {
        "id", "category", "priority", "title", "summary", "affected_assets"
    }


def test_multiple_assets_are_related_by_sector() -> None:
    context = event("sector", asset="unused")
    object.__setattr__(context, "related_assets", ())
    object.__setattr__(context, "related_sectors", ("Technology",))
    facts = DailyFactsEngine().generate(
        (position("ARGOS2"), position("ARGOS1")), (context,)
    )
    assert facts[0]["affected_assets"] == ["ARGOS1", "ARGOS2"]


def test_duplicates_limit_and_priority_order() -> None:
    context = (
        event("low", importance=FactImportance.LOW),
        event("high", importance=FactImportance.HIGH),
        event("critical", importance=FactImportance.CRITICAL),
        event("medium", importance=FactImportance.MEDIUM),
        event("extra-a"), event("extra-b"), event("extra-c"),
        event("high", importance=FactImportance.HIGH, title="Duplicado por id"),
        event("different", title="Resultado de low"),
    )
    facts = DailyFactsEngine().generate((position("ARGOS1"),), context)
    assert len(facts) == 5
    assert [fact["priority"] for fact in facts] == [
        "HIGH", "HIGH", "MEDIUM", "MEDIUM", "MEDIUM"
    ]
    assert len({fact["id"] for fact in facts}) == len(facts)
    assert len({fact["title"] for fact in facts}) == len(facts)


def test_recommendation_language_is_never_emitted() -> None:
    context = (
        event("buy", description="Recomendação: comprar o ativo."),
        event("fact", description="O dividendo foi anunciado."),
    )
    facts = DailyFactsEngine().generate((position("ARGOS1"),), context)
    assert [fact["id"] for fact in facts] == ["fact"]
    assert "comprar" not in repr(facts).casefold()
