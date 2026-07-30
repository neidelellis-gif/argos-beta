"""Tests for priorities derived exclusively from structured analyses."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
import re

import pytest

from backend.daily_priority_engine import DailyPriorityEngine
from backend.models import PortfolioOwner, PortfolioPosition


def position(asset: str = "ARGOS1") -> PortfolioPosition:
    return PortfolioPosition(
        "UBS", PortfolioOwner.JOLIKA, "1", "Equities", "Technology", asset,
        asset, "TICKER", Decimal("1"), None, None, "USD", None,
        date(2026, 7, 30), "fixture",
    )


def analysis(
    identifier: str,
    *,
    kind: str = "ANALYZE",
    priority: str = "MEDIUM",
    title: str | None = None,
    assets: tuple[str, ...] = ("ARGOS1",),
) -> dict[str, object]:
    return {
        "id": identifier,
        "type": kind,
        "priority": priority,
        "title": title or f"Analisar tema {identifier}",
        "summary": f"Contexto estruturado de {identifier}.",
        "related_facts": [f"fact-{identifier}"],
        "affected_assets": list(assets),
    }


def test_no_analysis_and_single_analysis_behavior() -> None:
    engine = DailyPriorityEngine()
    assert engine.generate((), ()) == []
    result = engine.generate((analysis("one"),), ())
    assert len(result) == 1
    assert result[0]["type"] == "ANALYZE"
    assert result[0]["related_analyses"] == ["one"]


def test_single_decide_analysis_preserves_type_without_execution_language() -> None:
    result = DailyPriorityEngine().generate(
        (analysis("decision", kind="DECIDE", priority="HIGH"),), (position(),)
    )
    assert result[0]["type"] == "DECIDE"
    assert "decisão a ser examinada" in str(result[0]["summary"])


def test_two_independent_and_more_than_two_respect_limit_and_order() -> None:
    items = (
        analysis("low", priority="LOW", assets=("L",)),
        analysis("medium", assets=("M",)),
        analysis("high-analyze", priority="HIGH", assets=("HA",)),
        analysis("high-decide", kind="DECIDE", priority="HIGH", assets=("HD",)),
    )
    result = DailyPriorityEngine().generate(items, ())
    assert len(result) == 2
    assert [item["related_analyses"] for item in result] == [
        ["high-decide"], ["high-analyze"],
    ]


@pytest.mark.parametrize("level", ("HIGH", "MEDIUM", "LOW"))
def test_official_priority_levels_are_preserved(level: str) -> None:
    result = DailyPriorityEngine().generate((analysis("one", priority=level),), ())
    assert result[0]["priority"] == level


def test_critical_is_normalized_to_high() -> None:
    result = DailyPriorityEngine().generate((analysis("one", priority="CRITICAL"),), ())
    assert result[0]["priority"] == "HIGH"


def test_related_analyses_group_by_shared_assets_and_preserve_assets() -> None:
    items = (
        analysis("a", assets=("A",)),
        analysis("b", assets=("A", "B")),
        analysis("c", assets=("B",)),
    )
    result = DailyPriorityEngine().generate(items, ())
    assert len(result) == 1
    assert result[0]["related_analyses"] == ["a", "b", "c"]
    assert result[0]["affected_assets"] == ["A", "B"]


def test_duplicates_by_generated_id_title_and_relation_are_removed() -> None:
    same_title = (
        analysis("a", title="Tema único", assets=("A",)),
        analysis("b", title="Tema  unico!", assets=("B",)),
    )
    result = DailyPriorityEngine().generate(same_title, ())
    assert len(result) == 1

    duplicate_id = (analysis("same", assets=("A",)), analysis("same", assets=("B",)))
    assert len(DailyPriorityEngine().generate(duplicate_id, ())) == 1


def test_deterministic_order_is_independent_from_input_order() -> None:
    items = (
        analysis("z", priority="HIGH", title="Z", assets=("Z",)),
        analysis("a", priority="HIGH", title="A", assets=("A",)),
    )
    engine = DailyPriorityEngine()
    assert engine.generate(items, ()) == engine.generate(tuple(reversed(items)), ())


def test_inputs_remain_immutable() -> None:
    analyses = [analysis("one")]
    positions = [position()]
    before_analyses = deepcopy(analyses)
    before_positions = deepcopy(positions)
    DailyPriorityEngine().generate(analyses, positions)
    assert analyses == before_analyses
    assert positions == before_positions


@pytest.mark.parametrize(
    "phrase",
    (
        "comprar", "vender", "aumentar posição", "reduzir posição",
        "reforçar posição", "liquidar", "entrar no ativo", "sair do ativo",
        "aplicar", "resgatar", "buy", "sell", "increase position",
        "reduce position",
    ),
)
def test_explicit_recommendation_language_is_discarded(phrase: str) -> None:
    item = analysis("bad")
    item["summary"] = f"É necessário {phrase}."
    assert DailyPriorityEngine().generate((item,), ()) == []


def test_contract_has_exact_fields_and_no_recommendation() -> None:
    result = DailyPriorityEngine().generate((analysis("one"),), ())[0]
    assert set(result) == {
        "id", "type", "priority", "title", "summary",
        "related_analyses", "affected_assets",
    }
    forbidden = re.compile(r"\b(comprar|vender|buy|sell)\b", re.IGNORECASE)
    assert not forbidden.search(f"{result['title']} {result['summary']}")


@pytest.mark.parametrize(
    "invalid",
    (
        {},
        {"id": "partial"},
        analysis("bad", kind="EXECUTE"),
        analysis("bad", priority="URGENT"),
    ),
)
def test_invalid_structures_are_discarded_without_partial_priority(
    invalid: dict[str, object],
) -> None:
    assert DailyPriorityEngine().generate((invalid,), ()) == []


def test_noncanonical_positions_are_rejected_but_positions_are_not_required() -> None:
    assert DailyPriorityEngine().generate((analysis("one"),), ())
    with pytest.raises(TypeError, match="PortfolioPosition"):
        DailyPriorityEngine().generate((analysis("one"),), ({},))  # type: ignore[arg-type]
