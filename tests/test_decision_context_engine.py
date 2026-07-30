import copy
from datetime import date

from backend.decision_context import validate_decision_profile
from backend.decision_context_engine import DecisionContextEngine, FIELDS
from tests.test_decision_context import profile_data


def test_no_profile_or_no_relations_produces_no_artificial_context():
    engine = DecisionContextEngine()
    assert engine.generate(None) == ()
    assert engine.generate(validate_decision_profile(profile_data())) == ()


def test_explicit_conflict_has_exact_contract_traceability_and_is_immutable():
    profile = validate_decision_profile(profile_data(capital_preservation_level="CRITICAL"))
    impacts = [{"id": "impact-1", "impact_level": "HIGH", "impact_direction": "UNCERTAIN",
                "affected_assets": ["GLD"]}]
    before = copy.deepcopy(impacts)
    contexts = DecisionContextEngine().generate(profile, impact_assessments=impacts)
    conflict = next(item for item in contexts if item["context_type"] == "CONTEXT_CONFLICT")
    assert tuple(conflict) == FIELDS
    assert conflict["related_impacts"] == ["impact-1"]
    assert conflict["related_assets"] == ["gld"]
    assert conflict["limitations"] == ["A direção do impacto permanece incerta."]
    assert impacts == before


def test_restriction_uses_normalized_equality_not_partial_matching():
    profile = validate_decision_profile(profile_data(restricted_assets=["PETR4"]))
    engine = DecisionContextEngine()
    assert not engine.generate(profile, facts=[{"id": "f", "related_assets": ["PETR"]}])
    contexts = engine.generate(profile, facts=[{"id": "f", "related_assets": [" petr4 "]}])
    assert contexts[0]["context_type"] == "RESTRICTION_CONTEXT"


def test_horizon_objective_concentration_order_limit_and_determinism():
    profile = validate_decision_profile(profile_data(
        primary_objectives=["INCOME"], secondary_objectives=[], restricted_assets=["AAA"],
        restricted_sectors=["ENERGY"], restricted_currencies=["USD"],
    ))
    event = {"id": "e1", "event_type": "DIVIDEND", "event_date": "2026-08-01",
             "asset_identifiers": ["AAA"], "sectors": ["ENERGY"], "currencies": ["USD"],
             "markets": ["UNITED_STATES"]}
    positions = [
        {"identifier": "AAA", "asset_name": "A", "currency": "USD"},
        {"identifier": "AAA", "asset_name": "B", "currency": "USD"},
    ]
    first = DecisionContextEngine().generate(
        profile=profile, market_agenda=[event], positions=positions,
        reference_date=date(2026, 7, 30),
    )
    second = DecisionContextEngine().generate(
        profile=profile, market_agenda=[event], positions=positions,
        reference_date=date(2026, 7, 30),
    )
    assert first == second and len(first) == 5
    assert first[0]["relevance_level"] == "HIGH"
    assert {item["context_type"] for item in first} >= {"RESTRICTION_CONTEXT", "HORIZON_ALIGNMENT", "OBJECTIVE_ALIGNMENT"}
    rendered = str(first).casefold()
    assert all(term not in rendered for term in ("comprar", "vender", "buy", "sell"))
