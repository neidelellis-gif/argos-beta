"""Integrated stability checks for the official post-Marco 15 daily flow."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from backend.connectors import bradesco_connector, santander_connector, ubs_connector
from backend.connectors.contract import PortfolioConnector
from backend.connectors.registry import ConnectorRegistry
from backend.daily_experience import (
    DailyExperienceComposer,
    DailyExperienceError,
    DailyExperienceStatus,
)
from backend.daily_orchestrator import (
    DailyOrchestrationError,
    DailyOrchestrationStage,
    DailyOrchestrationStatus,
    DailyOrchestrator,
    DailyStageStatus,
)
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshotBuilder
from backend.daily_priority import DailyPriorityAction, DailyPriorityEngine
from backend.import_validation import ImportValidationEngine, ImportValidationStatus
from backend.important_facts import (
    FactCandidate,
    FactCategory,
    FactImportance,
    ImportantFactsEngine,
)
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_consolidation import PortfolioConsolidationEngine
from backend.portfolio_impact import PortfolioImpactEngine


REFERENCE_DATE = date(2026, 7, 30)
NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def _position(
    institution: str,
    owner: PortfolioOwner,
    currency: str,
    identifier: str,
) -> PortfolioPosition:
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account="audit",
        asset_class="Equities",
        asset_subclass="Technology",
        asset_name=identifier,
        identifier=identifier,
        identifier_type="TICKER",
        quantity=Decimal("2"),
        unit_price=Decimal("10.25"),
        market_value=Decimal("20.50"),
        currency=currency,
        portfolio_weight=None,
        reference_date=REFERENCE_DATE,
        source_file="synthetic-audit-fixture",
    )


POSITIONS = (
    _position("UBS", PortfolioOwner.JOLIKA, "USD", "UBS1"),
    _position("Santander", PortfolioOwner.JOLIKA, "BRL", "SAN1"),
    _position("Bradesco", PortfolioOwner.NEI, "BRL", "BRA1"),
)


def _candidate(
    identifier: str,
    institution: str | None = None,
    currency: str | None = None,
    importance: FactImportance = FactImportance.HIGH,
) -> FactCandidate:
    return FactCandidate(
        identifier,
        f"Auditable fact {identifier}",
        "Structured evidence without a recommendation",
        "Synthetic audit source",
        NOW - timedelta(hours=1),
        importance,
        FactCategory.MARKETS,
        urgency=importance,
        related_institutions=(institution,) if institution else (),
        related_currencies=(currency,) if currency else (),
    )


def _orchestrator(
    snapshot_builder=None,
    facts_engine=None,
    impact_engine=None,
    priority_engine=None,
) -> DailyOrchestrator:
    return DailyOrchestrator(
        snapshot_builder or DailyPortfolioSnapshotBuilder(clock=lambda: NOW),
        facts_engine or ImportantFactsEngine(clock=lambda: NOW),
        impact_engine or PortfolioImpactEngine(clock=lambda: NOW),
        priority_engine or DailyPriorityEngine(clock=lambda: NOW),
        clock=lambda: NOW,
    )


def _run(
    positions: tuple[PortfolioPosition, ...],
    candidates: tuple[FactCandidate, ...],
):
    reports = {}
    validator = ImportValidationEngine()
    for position in positions:
        key = (position.owner, position.institution, position.currency)
        reports[key] = validator.validate((position,))
        assert reports[key].status is not ImportValidationStatus.REJECTED

    consolidated = PortfolioConsolidationEngine().consolidate(positions)
    result = _orchestrator().run(positions, candidates, REFERENCE_DATE, reports)
    experience = DailyExperienceComposer(clock=lambda: NOW).compose(result)
    return consolidated, result, experience


def test_registry_connector_and_complete_contract_chain() -> None:
    registry = ConnectorRegistry()
    for connector in (ubs_connector, santander_connector, bradesco_connector):
        registry.register(cast(PortfolioConnector, connector))

    assert all(isinstance(connector, PortfolioConnector) for connector in registry.active())
    assert tuple(connector.connector_id for connector in registry.active()) == (
        "ubs", "santander", "bradesco",
    )
    connector_positions = (
        ubs_connector._to_portfolio_position(
            {"account": "1", "symbol": "UBS1", "name": "UBS1", "asset_class": "Equities", "currency": "USD", "value": "20.50", "weight": None},
            "audit.csv",
        ),
        santander_connector._to_portfolio_position(
            {"account": "2", "symbol": "SAN1", "name": "SAN1", "asset_class": "Equities", "currency": "BRL", "value": "20.50", "weight": None},
            "audit.xlsx",
        ),
        bradesco_connector._to_portfolio_position(
            {"name": "BRA1", "asset_class": "Equities", "asset_subclass": "Technology", "quantity": Decimal("2"), "price": Decimal("10.25"), "gross": Decimal("20.50"), "weight": None},
            "audit.txt",
        ),
    )
    consolidated, orchestration, experience = _run(
        connector_positions,
        tuple(_candidate(f"fact-{index}", position.institution) for index, position in enumerate(connector_positions)),
    )

    assert consolidated.report.statistics.consolidated_value_by_currency == {
        "BRL": Decimal("41.00"), "USD": Decimal("20.50"),
    }
    assert orchestration.status is DailyOrchestrationStatus.COMPLETED
    assert tuple(stage.stage for stage in orchestration.stages) == tuple(DailyOrchestrationStage)
    assert orchestration.snapshot is not None
    assert orchestration.snapshot.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert orchestration.snapshot.institutions == ("Bradesco", "Santander", "UBS")
    assert orchestration.snapshot.currencies == ("BRL", "USD")
    assert experience.summary.priority_count == 3
    assert experience.summary.analysis_count == 2
    assert experience.status is DailyExperienceStatus.DECISION_REQUIRED
    assert "recommend" not in repr(experience).casefold()


@pytest.mark.parametrize(
    "positions",
    ((), POSITIONS[:1], POSITIONS[1:2], POSITIONS[2:], POSITIONS[:2], POSITIONS),
)
def test_empty_owner_and_institution_combinations(
    positions: tuple[PortfolioPosition, ...],
) -> None:
    _, result, experience = _run(positions, ())
    assert result.snapshot is not None
    assert result.snapshot.consolidated.gross_value_by_currency == (
        {} if not positions else {
            currency: sum(
                (item.market_value for item in positions if item.currency == currency and item.market_value is not None),
                Decimal("0"),
            )
            for currency in sorted({item.currency for item in positions if item.currency})
        }
    )
    assert experience.status is DailyExperienceStatus.NO_ACTION_REQUIRED
    assert experience.facts == experience.priorities == experience.analyses == ()


def test_global_analyze_decide_limits_and_no_artificial_items() -> None:
    candidates = (
        _candidate("global"),
        _candidate("analyze", currency="USD", importance=FactImportance.MEDIUM),
        *tuple(_candidate(f"decide-{index}", institution="UBS") for index in range(5)),
    )
    _, result, experience = _run(POSITIONS, candidates)
    assert result.important_facts is not None
    assert result.portfolio_impacts is not None
    assert result.daily_priorities is not None
    assert len(result.important_facts.important_facts) <= 5
    assert len(result.daily_priorities.priorities) <= 3
    assert len(experience.analyses) <= 2
    selected_fact_ids = {fact.id for fact in result.important_facts.important_facts}
    assert {impact.fact_id for impact in result.portfolio_impacts.impacts} == selected_fact_ids
    assert {priority.fact_id for priority in result.daily_priorities.priorities} <= selected_fact_ids
    assert any(priority.action is DailyPriorityAction.DECIDE for priority in result.daily_priorities.priorities)

    _, global_result, global_experience = _run(POSITIONS, (_candidate("global"),))
    assert global_result.important_facts is not None
    assert global_result.portfolio_impacts is not None
    assert tuple(fact.id for fact in global_result.important_facts.important_facts) == ("global",)
    assert global_result.portfolio_impacts.impacts[0].impact_level.value == "NONE"
    assert global_experience.facts[0].fact_id == "global"
    assert global_experience.priorities == global_experience.analyses == ()


def test_controlled_clock_is_deterministic_idempotent_order_independent_and_immutable() -> None:
    candidates = tuple(_candidate(f"fact-{item.institution}", item.institution) for item in POSITIONS)
    before_positions = repr(POSITIONS)
    before_candidates = repr(candidates)
    first = _run(POSITIONS, candidates)
    second = _run(tuple(reversed(POSITIONS)), tuple(reversed(candidates)))

    assert first == second
    assert repr(POSITIONS) == before_positions
    assert repr(candidates) == before_candidates
    snapshot = first[1].snapshot
    assert snapshot is not None
    with pytest.raises(FrozenInstanceError):
        setattr(snapshot, "owners", ())
    with pytest.raises(TypeError):
        cast(dict[str, Decimal], snapshot.consolidated.gross_value_by_currency)["USD"] = Decimal("0")


class _FailingStage:
    def __init__(self, method: str) -> None:
        self.method = method

    def build(self, *args, **kwargs):
        assert self.method == "build"
        raise RuntimeError("sensitive portfolio value")

    def select(self, *args, **kwargs):
        assert self.method == "select"
        raise RuntimeError("sensitive portfolio value")


@pytest.mark.parametrize(
    ("stage", "dependency", "method"),
    (
        (DailyOrchestrationStage.SNAPSHOT, "snapshot_builder", "build"),
        (DailyOrchestrationStage.IMPORTANT_FACTS, "facts_engine", "select"),
        (DailyOrchestrationStage.PORTFOLIO_IMPACT, "impact_engine", "build"),
        (DailyOrchestrationStage.DAILY_PRIORITY, "priority_engine", "build"),
    ),
)
def test_each_orchestration_failure_is_safe_chained_and_stops_later_stages(
    stage: DailyOrchestrationStage, dependency: str, method: str,
) -> None:
    kwargs = {dependency: _FailingStage(method)}
    with pytest.raises(DailyOrchestrationError) as captured:
        _orchestrator(**kwargs).run(POSITIONS, (_candidate("fact", "UBS"),), REFERENCE_DATE)

    error = captured.value
    statuses = tuple(item.status for item in error.result.stages)
    failed_index = tuple(DailyOrchestrationStage).index(stage)
    assert error.stage is stage
    assert statuses[:failed_index] == (DailyStageStatus.COMPLETED,) * failed_index
    assert statuses[failed_index] is DailyStageStatus.FAILED
    assert statuses[failed_index + 1 :] == (DailyStageStatus.SKIPPED,) * (3 - failed_index)
    assert isinstance(error.__cause__, RuntimeError)
    assert "sensitive portfolio value" not in str(error)
    assert "Traceback" not in repr(error.result)
    with pytest.raises(DailyExperienceError, match="not completed"):
        DailyExperienceComposer(clock=lambda: NOW).compose(error.result)


def test_composer_failure_is_typed_chained_and_never_becomes_empty_success() -> None:
    _, orchestration, _ = _run((), ())

    def failing_clock() -> datetime:
        raise RuntimeError("sensitive clock detail")

    with pytest.raises(DailyExperienceError) as captured:
        DailyExperienceComposer(clock=failing_clock).compose(orchestration)
    assert captured.value.error_type == "CLOCK_ERROR"
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert "sensitive clock detail" not in str(captured.value)
    assert "Nada exige" not in str(captured.value)
