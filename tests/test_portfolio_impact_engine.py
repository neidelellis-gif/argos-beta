from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_impact_engine import FIELDS, PortfolioImpactAssessmentEngine


def position(identifier="GLD", name="Gold ETF", institution="UBS", asset_class="ETF",
             sector="METALS", currency="USD", market="US", country="US"):
    item = PortfolioPosition(institution, PortfolioOwner.JOLIKA, "1", asset_class, sector,
        name, identifier, "TICKER", Decimal("1"), None, None, currency, None,
        date(2026, 7, 30), "fixture")
    object.__setattr__(item, "market", market)
    object.__setattr__(item, "country", country)
    return item


def source(identifier="fact-1", priority="HIGH", **extra):
    data = {"id": identifier, "priority": priority, "title": "Fato relevante",
            "summary": "Relação estruturada com a carteira."}
    data.update(extra)
    return data


def generate(item, positions=None, event=False):
    args = ([], [item], positions or [position()]) if event else ([item], [], positions or [position()])
    return PortfolioImpactAssessmentEngine().generate(*args)


def test_empty_inputs_and_sources_without_portfolio_or_relation_do_not_invent_assessments():
    engine = PortfolioImpactAssessmentEngine()
    assert engine.generate([], [], []) == []
    assert engine.generate([source(related_assets=["GLD"])], [], []) == []
    assert engine.generate([], [source(affected_assets=["GLD"])], []) == []
    assert generate(source(related_assets=["OTHER"])) == []


@pytest.mark.parametrize(("field", "value", "relationship", "confidence"), [
    ("related_assets", [" gld "], "DIRECT_ASSET", "HIGH"),
    ("asset_names", ["gold etf"], "ASSET_NAME", "HIGH"),
    ("related_institutions", ["ubs"], "INSTITUTION", "HIGH"),
    ("related_sectors", ["metals"], "SECTOR", "MEDIUM"),
    ("asset_classes", ["etf"], "ASSET_CLASS", "MEDIUM"),
    ("related_currencies", ["usd"], "CURRENCY", "MEDIUM"),
    ("markets", ["us"], "MARKET", "MEDIUM"),
    ("country", "us", "COUNTRY", "LOW"),
])
def test_all_official_relationships_are_exact_and_traceable(field, value, relationship, confidence):
    result = generate(source(**{field: value}))[0]
    affected = result["affected_positions"]
    factors = result["impact_factors"]
    assert isinstance(affected, list) and isinstance(affected[0], dict)
    assert isinstance(factors, list) and isinstance(factors[0], dict)
    assert affected[0]["relationship_type"] == relationship
    assert result["confidence"] == confidence
    assert set(affected[0]) == {
        "position_id", "asset_identifier", "asset_name", "institution", "relationship_type"}
    assert set(factors[0]) == {"factor_type", "factor_value", "description"}


def test_partial_asset_match_is_forbidden_and_strongest_relationship_wins():
    assert generate(source(related_assets=["GL"], related_currencies=["EUR"])) == []
    item = generate(source(related_assets=["GLD"], related_currencies=["USD"]))[0]
    affected = item["affected_positions"]
    assert isinstance(affected, list) and isinstance(affected[0], dict)
    assert affected[0]["relationship_type"] == "DIRECT_ASSET"


@pytest.mark.parametrize(("priority", "relation", "expected"), [
    ("HIGH", {"related_assets": ["GLD"]}, "HIGH"),
    ("MEDIUM", {"related_assets": ["GLD"]}, "MEDIUM"),
    ("HIGH", {"related_sectors": ["METALS"]}, "MEDIUM"),
    ("MEDIUM", {"related_sectors": ["METALS"]}, "LOW"),
])
def test_impact_level_is_deterministic(priority, relation, expected):
    assert generate(source(priority=priority, **relation))[0]["impact_level"] == expected


@pytest.mark.parametrize("direction", ["POSITIVE", "NEGATIVE", "MIXED"])
def test_explicit_official_direction_is_preserved(direction):
    assert generate(source(related_assets=["GLD"], impact_direction=direction))[0]["impact_direction"] == direction


def test_direction_defaults_to_uncertain_and_critical_moderate_are_compatible():
    assert generate(source(priority="CRITICAL", related_assets=["GLD"]))[0]["impact_direction"] == "UNCERTAIN"
    assert generate(source(priority="MODERATE", related_assets=["GLD"]))[0]["impact_level"] == "MEDIUM"


def test_one_origin_consolidates_multiple_positions_and_contract_is_exact():
    result = generate(source(related_currencies=["USD"]), [position(), position("EQIX", "Equinix")])
    affected = result[0]["affected_positions"]
    assert isinstance(affected, list)
    assert len(result) == 1 and len(affected) == 2
    assert tuple(result[0]) == FIELDS
    assert result[0]["related_facts"] == ["fact-1"] and result[0]["related_events"] == []


def test_duplicate_origin_order_and_limit_are_deterministic():
    facts = [source(f"f-{index}", related_assets=["GLD"], title=f"Title {index}") for index in range(7)]
    facts.append(dict(facts[0]))
    result = PortfolioImpactAssessmentEngine().generate(facts, [], [position()])
    assert len(result) == 5 and len({item["source_id"] for item in result}) == 5
    assert result == PortfolioImpactAssessmentEngine().generate(deepcopy(facts), [], [position()])


def test_recommendations_invalid_structures_and_missing_origins_are_rejected():
    assert generate(source(related_assets=["GLD"], summary="Comprar o ativo.")) == []
    assert generate({"priority": "HIGH", "title": "Sem origem", "summary": "Contexto", "related_assets": ["GLD"]}) == []
    with pytest.raises(TypeError):
        PortfolioImpactAssessmentEngine().generate(["invalid"], [], [])  # pyright: ignore[reportArgumentType]


def test_inputs_are_immutable_and_event_traceability_is_separate():
    facts = [source(related_assets=["GLD"])]
    events = [source("agenda-1", affected_assets=["GLD"])]
    positions = [position()]
    before = deepcopy((facts, events, positions))
    event_result = PortfolioImpactAssessmentEngine().generate(facts, events, positions)
    assert (facts, events, positions) == before
    assert any(item["source_type"] == "MARKET_EVENT" and item["related_events"] == ["agenda-1"] for item in event_result)
