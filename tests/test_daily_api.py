"""Contract and integration tests for the stable daily API facade."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from types import MappingProxyType
from collections.abc import Mapping
from typing import cast

import pytest

import backend.daily_api as daily_api_module
from backend.daily_api import (
    DailyApiErrorCode,
    DailyApiFacade,
    DailyApiRequest,
    DailyApiStatus,
    daily_api_response_to_dict,
)
from backend.daily_experience import DailyExperienceComposer, DailyExperienceError
from backend.daily_orchestrator import DailyOrchestrator
from backend.daily_portfolio_snapshot import (
    DailyPortfolioSnapshotBuilder,
    ValidationReportKey,
)
from backend.daily_priority import DailyPriorityEngine
from backend.import_validation import ImportValidationReport
from backend.important_facts import (
    FactCandidate,
    FactCategory,
    FactImportance,
    ImportantFactsEngine,
)
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_impact import PortfolioImpactEngine


REFERENCE_DATE = date(2026, 7, 30)
NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def _position(
    institution: str = "UBS",
    owner: PortfolioOwner = PortfolioOwner.JOLIKA,
    currency: str = "USD",
    identifier: str = "ARGOS1",
) -> PortfolioPosition:
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account="test",
        asset_class="Equities",
        asset_subclass="Technology",
        asset_name=identifier,
        identifier=identifier,
        identifier_type="TICKER",
        quantity=Decimal("2"),
        unit_price=Decimal("10"),
        market_value=Decimal("20"),
        currency=currency,
        portfolio_weight=None,
        reference_date=REFERENCE_DATE,
        source_file="private-fixture.csv",
    )


def _candidate(
    identifier: str,
    *,
    institution: str | None = None,
    currency: str | None = None,
    importance: FactImportance = FactImportance.HIGH,
) -> FactCandidate:
    return FactCandidate(
        id=identifier,
        title=f"Fact {identifier}",
        description="Structured evidence",
        source="Private source",
        published_at=NOW - timedelta(hours=1),
        importance=importance,
        category=FactCategory.MARKETS,
        urgency=importance,
        related_institutions=(institution,) if institution else (),
        related_currencies=(currency,) if currency else (),
    )


def _orchestrator() -> DailyOrchestrator:
    return DailyOrchestrator(
        DailyPortfolioSnapshotBuilder(clock=lambda: NOW),
        ImportantFactsEngine(clock=lambda: NOW),
        PortfolioImpactEngine(clock=lambda: NOW),
        DailyPriorityEngine(clock=lambda: NOW),
        clock=lambda: NOW,
    )


def _facade() -> DailyApiFacade:
    return DailyApiFacade(
        orchestrator=_orchestrator(),
        composer=DailyExperienceComposer(clock=lambda: NOW),
        clock=lambda: NOW,
    )


def _request(
    candidates: tuple[FactCandidate, ...] = (),
    positions: tuple[PortfolioPosition, ...] = (_position(),),
) -> DailyApiRequest:
    return DailyApiRequest(positions, candidates, REFERENCE_DATE)


def test_valid_request_executes_real_complete_flow() -> None:
    response = _facade().execute(
        _request((_candidate("decision", institution="UBS"),))
    )

    assert response.status is DailyApiStatus.SUCCESS
    assert response.header is not None
    assert response.message is not None
    assert response.summary is not None
    assert response.error is None
    assert response.header.period == "MORNING"
    assert response.facts[0].id == "decision"


@pytest.mark.parametrize(
    ("candidates", "status", "action", "attention", "decision"),
    (
        ((), "NO_ACTION_REQUIRED", None, False, False),
        (
            (_candidate("attention", currency="USD", importance=FactImportance.MEDIUM),),
            "ATTENTION_REQUIRED",
            "Analisar",
            True,
            False,
        ),
        (
            (_candidate("decision", institution="UBS"),),
            "DECISION_REQUIRED",
            "Decidir",
            True,
            True,
        ),
    ),
)
def test_official_experience_states_are_preserved(
    candidates: tuple[FactCandidate, ...],
    status: str,
    action: str | None,
    attention: bool,
    decision: bool,
) -> None:
    response = _facade().execute(_request(candidates))

    assert response.experience_status == status
    assert response.summary is not None
    assert response.summary.requires_attention is attention
    assert response.summary.requires_decision is decision
    if action is None:
        assert response.priorities == response.analyses == ()
    else:
        assert response.priorities
        assert response.analyses[0].action == action


def test_limits_blocks_order_visibility_and_titles_are_preserved() -> None:
    candidates = tuple(
        _candidate(f"fact-{index}", institution="UBS") for index in range(8)
    )
    response = _facade().execute(_request(candidates))

    assert len(response.facts) <= 5
    assert len(response.priorities) <= 3
    assert len(response.analyses) <= 2
    assert tuple(block.type for block in response.blocks) == (
        "FACTS", "PRIORITIES", "ANALYSES"
    )
    assert tuple(block.title for block in response.blocks) == (
        "Fatos importantes", "Prioridades do dia", "Análises"
    )
    assert len(response.blocks) == 3
    assert tuple(block.visible for block in response.blocks) == (True, True, True)

    empty = _facade().execute(_request())
    assert len(empty.blocks) == 3
    assert tuple(block.visible for block in empty.blocks) == (False, False, False)


def test_success_serialization_is_json_safe_ordered_and_detached() -> None:
    response = _facade().execute(
        _request((_candidate("decision", institution="UBS"),))
    )
    serialized = daily_api_response_to_dict(response)

    json.dumps(serialized)
    assert serialized["status"] == "SUCCESS"
    assert serialized["generated_at"] == "2026-07-30T12:00:00+00:00"
    assert serialized["error"] is None
    assert [block["type"] for block in cast(list[dict[str, object]], serialized["blocks"])] == [
        "FACTS", "PRIORITIES", "ANALYSES"
    ]
    cast(list[dict[str, object]], serialized["facts"])[0]["text"] = "changed"
    assert response.facts[0].text == "Fact decision"


@pytest.mark.parametrize("field", ("positions", "fact_candidates"))
def test_list_collections_return_invalid_request_without_running(
    field: str,
) -> None:
    request = _request()
    invalid = DailyApiRequest(
        positions=cast(tuple[PortfolioPosition, ...], [] if field == "positions" else request.positions),
        fact_candidates=cast(tuple[FactCandidate, ...], [] if field == "fact_candidates" else ()),
        reference_date=REFERENCE_DATE,
    )
    response = _facade().execute(invalid)

    assert response.status is DailyApiStatus.ERROR
    assert response.error is not None
    assert response.error.code is DailyApiErrorCode.INVALID_REQUEST
    assert response.error.stage == "REQUEST"


@pytest.mark.parametrize("field", ("positions", "fact_candidates"))
def test_invalid_collection_items_return_invalid_request(field: str) -> None:
    invalid = DailyApiRequest(
        positions=cast(tuple[PortfolioPosition, ...], (object(),)) if field == "positions" else (_position(),),
        fact_candidates=cast(tuple[FactCandidate, ...], (object(),)) if field == "fact_candidates" else (),
        reference_date=REFERENCE_DATE,
    )

    response = _facade().execute(invalid)
    assert response.error is not None
    assert response.error.code is DailyApiErrorCode.INVALID_REQUEST


class _FailingFactsEngine(ImportantFactsEngine):
    def select(self, candidates, snapshot):
        raise RuntimeError("market_value=999 source_file=secret.csv")


class _TrackingComposer(DailyExperienceComposer):
    called = False

    def compose(self, result):
        self.called = True
        return super().compose(result)


def test_orchestration_failure_is_safe_and_skips_composer() -> None:
    orchestrator = DailyOrchestrator(
        DailyPortfolioSnapshotBuilder(clock=lambda: NOW),
        _FailingFactsEngine(clock=lambda: NOW),
        PortfolioImpactEngine(clock=lambda: NOW),
        DailyPriorityEngine(clock=lambda: NOW),
        clock=lambda: NOW,
    )
    composer = _TrackingComposer(clock=lambda: NOW)
    response = DailyApiFacade(orchestrator, composer, lambda: NOW).execute(_request())
    serialized = daily_api_response_to_dict(response)

    assert response.error is not None
    assert response.error.code is DailyApiErrorCode.ORCHESTRATION_ERROR
    assert response.error.stage == "IMPORTANT_FACTS"
    assert composer.called is False
    assert "secret" not in repr(response)
    assert serialized["facts"] == serialized["blocks"] == []
    assert serialized["header"] is serialized["summary"] is None


class _ExperienceFailure(DailyExperienceComposer):
    def compose(self, result):
        raise DailyExperienceError("SECRET", "quantity=200")


class _UnexpectedFailure(DailyExperienceComposer):
    def compose(self, result):
        raise RuntimeError("traceback unit_price source_file private fact")


@pytest.mark.parametrize(
    ("composer", "code", "stage"),
    (
        (_ExperienceFailure(clock=lambda: NOW), DailyApiErrorCode.EXPERIENCE_ERROR, "EXPERIENCE"),
        (_UnexpectedFailure(clock=lambda: NOW), DailyApiErrorCode.INTERNAL_ERROR, "INTERNAL"),
    ),
)
def test_composition_failures_never_return_partial_or_sensitive_data(
    composer: DailyExperienceComposer,
    code: DailyApiErrorCode,
    stage: str,
) -> None:
    response = DailyApiFacade(_orchestrator(), composer, lambda: NOW).execute(_request())
    value = repr(response) + json.dumps(daily_api_response_to_dict(response))

    assert response.error is not None
    assert response.error.code is code
    assert response.error.stage == stage
    assert response.facts == response.priorities == response.analyses == ()
    for forbidden in ("traceback", "unit_price", "source_file", "quantity=200"):
        assert forbidden not in value


@pytest.mark.parametrize("clock", (lambda: object(), lambda: datetime(2026, 7, 30)))
def test_invalid_clock_returns_internal_error(clock) -> None:
    response = DailyApiFacade(_orchestrator(), DailyExperienceComposer(clock=lambda: NOW), clock).execute(_request())

    assert response.error is not None
    assert response.error.code is DailyApiErrorCode.INTERNAL_ERROR
    assert response.error.stage == "INTERNAL"


def test_clock_is_normalized_to_utc_and_execution_is_deterministic() -> None:
    def offset_clock() -> datetime:
        return datetime(
            2026, 7, 30, 9, tzinfo=timezone(timedelta(hours=-3))
        )

    facade = DailyApiFacade(
        _orchestrator(), DailyExperienceComposer(clock=lambda: NOW), offset_clock
    )
    request = _request((_candidate("decision", institution="UBS"),))

    first = facade.execute(request)
    second = facade.execute(request)
    assert first == second
    assert daily_api_response_to_dict(first) == daily_api_response_to_dict(second)
    assert first.generated_at == NOW
    assert first.generated_at.tzinfo is timezone.utc


def test_contracts_are_immutable_tuples_and_inputs_are_not_mutated() -> None:
    positions = (_position(),)
    candidates = (_candidate("decision", institution="UBS"),)
    reports: Mapping[ValidationReportKey, ImportValidationReport] = MappingProxyType({})
    request = DailyApiRequest(positions, candidates, REFERENCE_DATE, reports)
    before = (request, positions, candidates, dict(reports))

    response = _facade().execute(request)

    assert isinstance(response.facts, tuple)
    assert isinstance(response.blocks, tuple)
    assert before == (request, positions, candidates, dict(reports))
    with pytest.raises(FrozenInstanceError):
        setattr(response, "status", DailyApiStatus.ERROR)


def test_no_internal_or_financial_data_leaks_across_owners_and_currencies() -> None:
    positions = (
        _position("UBS", PortfolioOwner.JOLIKA, "USD", "JUSD"),
        _position("Santander", PortfolioOwner.JOLIKA, "BRL", "JBRL"),
        _position("Bradesco", PortfolioOwner.NEI, "BRL", "NBRL"),
    )
    response = _facade().execute(
        _request((_candidate("global"),), positions)
    )
    value = repr(response) + json.dumps(daily_api_response_to_dict(response))

    assert response.status is DailyApiStatus.SUCCESS
    for forbidden in (
        "DailyPortfolioSnapshot", "ImportantFactsResult", "PortfolioImpactResult",
        "DailyPriorityResult", "DailyOrchestrationResult", "traceback", "source_file",
        "market_value", "quantity", "unit_price", "Decimal", "JOLIKA", "NEI",
    ):
        assert forbidden not in value


def test_module_uses_only_the_official_orchestrator_import() -> None:
    assert daily_api_module.DailyOrchestrator.__module__ == "backend.daily_orchestrator"
