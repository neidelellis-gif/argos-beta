"""Contract and deterministic rule tests for the data quality engine."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from typing import Any, cast

from backend.data_quality_engine import DIAGNOSTIC_FIELDS, DataQualityEngine
from backend.decision_context import validate_decision_profile
from backend.models import PortfolioOwner
from backend.market_agenda import validate_market_agenda_event
from tests.test_decision_context import profile_data
from tests.test_market_agenda import event
from tests.test_portfolio_impact_engine import position


REFERENCE = date(2026, 7, 30)


def diagnose(positions=(), events=(), profile=None):
    return DataQualityEngine().diagnose(positions, events, profile, REFERENCE)


def test_empty_inputs_have_error_warning_info_and_exact_contract() -> None:
    result = diagnose()
    assert result["status"] == "ERROR"
    assert result["summary"] == {"errors": 1, "warnings": 1, "infos": 1}
    diagnostics = cast(list[dict[str, object]], result["diagnostics"])
    assert all(set(item) == DIAGNOSTIC_FIELDS for item in diagnostics)
    assert {item["severity"] for item in diagnostics} == {"ERROR", "WARNING", "INFO"}


def test_healthy_status_for_consistent_canonical_inputs() -> None:
    profile = validate_decision_profile(profile_data(review_date="2026-08-30"))
    agenda = validate_market_agenda_event(event(asset_identifiers=["GLD"]))
    result = diagnose((position(),), (agenda,), profile)
    assert result == {"status": "HEALTHY", "diagnostics": [],
                      "summary": {"errors": 0, "warnings": 0, "infos": 0}}


def test_duplicates_missing_fields_expired_events_and_overdue_review() -> None:
    item = position()
    incomplete = replace(item, identifier=None, currency=None, institution="")
    expired = validate_market_agenda_event(event(event_date="2026-07-29", asset_identifiers=["OTHER"]))
    profile = validate_decision_profile(profile_data(review_date="2026-07-29", base_currency="EUR"))
    comparable = replace(item, identifier="USD-ASSET", currency="USD")
    result = diagnose((incomplete, incomplete, comparable), (expired, expired), profile)
    ids = {item["id"] for item in cast(list[dict[str, object]], result["diagnostics"])}
    assert {"portfolio.duplicates", "portfolio.missing_identifier", "portfolio.missing_currency",
            "portfolio.missing_institution", "agenda.expired", "agenda.duplicates",
            "context.review_overdue", "cross.agenda_assets_missing", "cross.base_currency"} <= ids
    assert result["status"] == "WARNING"


def test_cross_validation_rejects_company_context_for_personal_portfolio() -> None:
    personal = replace(position(), owner=PortfolioOwner.NEI)
    profile = validate_decision_profile(profile_data(review_date="2026-08-30"))
    result = diagnose((personal,), (), profile)
    diagnostic = next(item for item in cast(list[dict[str, Any]], result["diagnostics"])
                      if item["id"] == "cross.company_personal")
    assert result["status"] == "ERROR"
    assert diagnostic["can_continue"] is False


def test_invalid_event_is_diagnosed_and_inputs_are_immutable() -> None:
    raw_positions = [position()]
    raw_events = [{"event_date": "30/07/2026"}]
    before = deepcopy(raw_events)
    result = DataQualityEngine().diagnose(raw_positions, cast(Any, raw_events), None, REFERENCE)
    ids = {item["id"] for item in cast(list[dict[str, object]], result["diagnostics"])}
    assert "agenda.invalid_dates" in ids
    assert raw_events == before
    assert raw_positions[0] is raw_positions[0]


def test_event_without_any_relationship_is_informational() -> None:
    unrelated = validate_market_agenda_event(event(
        institution=None, asset_identifiers=[], asset_names=[], asset_classes=[],
        currencies=[], markets=[], country=None,
    ))
    result = diagnose((position(),), (unrelated,),
                      validate_decision_profile(profile_data(review_date="2026-08-30")))
    assert any(item["id"] == "cross.events_unrelated"
               for item in cast(list[dict[str, object]], result["diagnostics"]))
