"""Tests for the isolated daily analysis engine."""

from datetime import date
from decimal import Decimal
import re
from typing import cast

from backend.daily_analysis_engine import DailyAnalysisEngine
from backend.models import PortfolioOwner, PortfolioPosition


def position(asset: str = "ARGOS1") -> PortfolioPosition:
    return PortfolioPosition(
        "UBS", PortfolioOwner.JOLIKA, "1", "Equities", "Technology", asset,
        asset, "TICKER", Decimal("1"), None, None, "USD", None,
        date(2026, 7, 30), "fixture",
    )


def fact(
    identifier: str,
    *,
    priority: str = "MEDIUM",
    title: str | None = None,
    assets: tuple[str, ...] = ("ARGOS1",),
) -> dict[str, object]:
    return {
        "id": identifier,
        "category": "CORPORATE",
        "priority": priority,
        "title": title or f"Fato {identifier}",
        "summary": f"Descrição objetiva {identifier}.",
        "affected_assets": list(assets),
    }


def test_no_facts_produces_no_analysis() -> None:
    assert DailyAnalysisEngine().generate((), (position(),)) == []


def test_one_fact_produces_complete_analysis_and_preserves_reference() -> None:
    source = fact("one")
    result = DailyAnalysisEngine().generate((source,), (position(),))
    assert len(result) == 1
    assert result[0]["type"] == "ANALYZE"
    assert result[0]["priority"] == "MEDIUM"
    assert result[0]["title"] == "Fato one"
    assert result[0]["related_facts"] == ["one"]
    assert set(result[0]) == {
        "id", "type", "priority", "title", "summary", "related_facts",
        "affected_assets",
    }
    assert result[0]["affected_assets"] == ["ARGOS1"]


def test_related_facts_are_grouped_transitively() -> None:
    facts = (
        fact("a", assets=("A",)),
        fact("b", assets=("A", "B")),
        fact("c", assets=("B",)),
    )
    result = DailyAnalysisEngine().generate(facts, (position(),))
    assert len(result) == 1
    assert result[0]["related_facts"] == ["a", "b", "c"]
    assert result[0]["title"] == "3 fatos relacionados sobre A e B"


def test_independent_facts_remain_independent_and_limit_is_two() -> None:
    facts = tuple(fact(name, assets=(name.upper(),)) for name in ("a", "b", "c", "d"))
    result = DailyAnalysisEngine().generate(facts, (position(),))
    assert len(result) == 2
    assert [item["related_facts"] for item in result] == [["a"], ["b"]]


def test_duplicates_by_id_or_normalized_title_are_removed() -> None:
    facts = (
        fact("same", title="Resultado trimestral"),
        fact("same", title="Outro título"),
        fact("other", title="Resultado  trimestral!"),
    )
    result = DailyAnalysisEngine().generate(facts, (position(),))
    assert result[0]["related_facts"] == ["same"]


def test_high_priority_uses_official_decide_type_without_recommendation() -> None:
    recommendation = fact("buy")
    recommendation["summary"] = "Recomendação: comprar e aumentar a posição."
    result = DailyAnalysisEngine().generate(
        (recommendation, fact("high", priority="HIGH")), (position(),)
    )
    assert result[0]["type"] == "DECIDE"
    assert result[0]["related_facts"] == ["high"]
    forbidden = re.compile(
        r"\b(comprar|vender|aumentar|reduzir|aportar|resgatar|buy|sell)\b",
        re.IGNORECASE,
    )
    assert not forbidden.search(f"{result[0]['title']} {result[0]['summary']}")


def test_order_is_stable_by_priority_title_and_id() -> None:
    facts = (
        fact("low", priority="LOW", title="A", assets=("L",)),
        fact("medium", title="Z", assets=("M",)),
        fact("high-z", priority="HIGH", title="Z", assets=("HZ",)),
        fact("high-a", priority="HIGH", title="A", assets=("HA",)),
    )
    engine = DailyAnalysisEngine()
    first = engine.generate(facts, (position(),))
    second = engine.generate(tuple(reversed(facts)), (position(),))
    assert first == second
    assert [item["related_facts"] for item in first] == [["high-a"], ["high-z"]]


def test_inputs_are_not_modified() -> None:
    source = fact("one")
    positions = (position(),)
    before = source.copy()
    before["affected_assets"] = list(cast(list[str], source["affected_assets"]))
    DailyAnalysisEngine().generate((source,), positions)
    assert source == before
