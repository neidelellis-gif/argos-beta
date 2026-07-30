import csv
import io
import json
from dataclasses import FrozenInstanceError

import pytest
from typing import Any, cast

from backend.decision_context import (
    CSV_FIELDS, DecisionContextValidationError, import_decision_profile,
    validate_decision_profile,
)


def profile_data(**changes):
    value = {
        "profile_id": "jolika-main", "profile_name": "Jolika — Perfil principal",
        "portfolio_scope": "COMPANY", "risk_level": "HIGH",
        "investment_horizon": "SHORT_TERM",
        "primary_objectives": ["CAPITAL_GROWTH", "DIVERSIFICATION"],
        "secondary_objectives": ["INCOME"], "liquidity_needs": "LOW",
        "capital_preservation_level": "MODERATE", "volatility_tolerance": "HIGH",
        "concentration_tolerance": "MODERATE", "restricted_assets": [],
        "restricted_asset_classes": [], "restricted_sectors": [],
        "restricted_currencies": [], "preferred_markets": ["UNITED_STATES"],
        "base_currency": "USD", "decision_frequency": "EVENT_DRIVEN",
        "review_date": "2026-07-30", "source_name": "Definição do usuário",
        "source_reference": "perfil-aprovado", "notes": "",
    }
    value.update(changes)
    return value


def test_valid_json_normalizes_medium_and_is_immutable():
    raw = json.dumps({"profile": profile_data(risk_level="MEDIUM")}).encode()
    profile = import_decision_profile("profile.json", raw)
    assert profile.risk_level.value == "MODERATE"
    with pytest.raises(FrozenInstanceError):
        setattr(profile, "profile_name", "changed")


def test_valid_csv_uses_pipe_collections():
    data = profile_data()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerow(cast(Any, {key: "|".join(value) if isinstance(value, list) else value for key, value in data.items()}))
    profile = import_decision_profile("profile.csv", buffer.getvalue().encode())
    assert [item.value for item in profile.primary_objectives] == ["CAPITAL_GROWTH", "DIVERSIFICATION"]


@pytest.mark.parametrize(("changes", "message"), [
    ({"portfolio_scope": "JOLIKA"}, "portfolio_scope"),
    ({"risk_level": "UNKNOWN"}, "risk_level"),
    ({"investment_horizon": "SOON"}, "investment_horizon"),
    ({"primary_objectives": ["PROFIT"]}, "primary_objectives"),
    ({"liquidity_needs": "CRITICAL"}, "liquidity_needs"),
    ({"capital_preservation_level": "VERY_HIGH"}, "capital_preservation_level"),
    ({"volatility_tolerance": "ANY"}, "volatility_tolerance"),
    ({"concentration_tolerance": "ANY"}, "concentration_tolerance"),
    ({"decision_frequency": "YEARLY"}, "decision_frequency"),
    ({"base_currency": "US"}, "moeda-base"),
    ({"review_date": "30/07/2026"}, "data de revisão"),
    ({"source_name": ""}, "source_name"),
    ({"restricted_assets": ["ABC", "abc"]}, "duplicados"),
    ({"preferred_markets": [str(i) for i in range(21)]}, "excede"),
    ({"notes": "x" * 2001}, "notes"),
])
def test_rejects_invalid_profiles(changes, message):
    with pytest.raises(DecisionContextValidationError, match=message):
        validate_decision_profile(profile_data(**changes))


@pytest.mark.parametrize(("name", "content"), [("p.json", b""), ("p.json", b"{}")])
def test_rejects_empty_or_missing_profile(name, content):
    with pytest.raises(DecisionContextValidationError):
        import_decision_profile(name, content)


def test_csv_requires_exactly_one_profile():
    content = ",".join(CSV_FIELDS) + "\n"
    with pytest.raises(DecisionContextValidationError, match="exatamente um"):
        import_decision_profile("p.csv", content.encode())
