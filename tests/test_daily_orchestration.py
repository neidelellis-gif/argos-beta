from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from backend.daily_orchestrator import (
    DailyOrchestrationError,
    DailyOrchestrationStage,
    DailyOrchestrationStatus,
    DailyOrchestrationSummary,
    DailyOrchestrator,
    DailyStageExecution,
    DailyStageStatus,
)
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshotBuilder
from backend.daily_priority import DailyPriorityEngine
from backend.important_facts import (
    FactCandidate,
    FactCategory,
    FactImportance,
    ImportantFactsEngine,
)
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_impact import PortfolioImpactEngine


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
REFERENCE_DATE = date(2026, 7, 30)


def position(
    institution: str, owner: PortfolioOwner, currency: str, identifier: str
) -> PortfolioPosition:
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account="official",
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
        source_file="fixture",
    )


POSITIONS = (
    position("UBS", PortfolioOwner.JOLIKA, "USD", "UBS1"),
    position("Santander", PortfolioOwner.JOLIKA, "BRL", "SAN1"),
    position("Bradesco", PortfolioOwner.NEI, "BRL", "BRA1"),
)


def candidate(identifier: str = "fact-1") -> FactCandidate:
    return FactCandidate(
        identifier,
        "Official portfolio fact",
        "Structured description",
        "Official source",
        NOW - timedelta(hours=1),
        FactImportance.HIGH,
        FactCategory.MARKETS,
        urgency=FactImportance.HIGH,
        related_institutions=("UBS",),
    )


class RecordingSnapshotBuilder(DailyPortfolioSnapshotBuilder):
    def __init__(self, calls: list[str], failure: bool = False) -> None:
        super().__init__()
        self.calls = calls
        self.failure = failure

    def build(self, positions, reference_date=None, validation_reports=None):
        self.calls.append("SNAPSHOT")
        if self.failure:
            raise RuntimeError("sensitive position must not escape")
        return replace(
            super().build(positions, reference_date, validation_reports), generated_at=NOW
        )


class RecordingFactsEngine(ImportantFactsEngine):
    def __init__(self, calls: list[str], failure: bool = False) -> None:
        super().__init__(clock=lambda: NOW)
        self.calls = calls
        self.failure = failure

    def select(self, candidates, snapshot):
        self.calls.append("IMPORTANT_FACTS")
        if self.failure:
            raise LookupError("sensitive fact must not escape")
        return super().select(candidates, snapshot)


class RecordingImpactEngine(PortfolioImpactEngine):
    def __init__(self, calls: list[str], failure: bool = False) -> None:
        super().__init__(clock=lambda: NOW)
        self.calls = calls
        self.failure = failure

    def build(self, snapshot, facts_result):
        self.calls.append("PORTFOLIO_IMPACT")
        if self.failure:
            raise ArithmeticError("sensitive value must not escape")
        return super().build(snapshot, facts_result)


class RecordingPriorityEngine(DailyPriorityEngine):
    def __init__(self, calls: list[str], failure: bool = False) -> None:
        super().__init__(clock=lambda: NOW)
        self.calls = calls
        self.failure = failure

    def build(self, snapshot, facts_result, impact_result):
        self.calls.append("DAILY_PRIORITY")
        if self.failure:
            raise KeyError("sensitive priority must not escape")
        return super().build(snapshot, facts_result, impact_result)


def orchestrator(
    calls: list[str] | None = None,
    failure: DailyOrchestrationStage | None = None,
) -> DailyOrchestrator:
    recorded = calls if calls is not None else []
    return DailyOrchestrator(
        RecordingSnapshotBuilder(recorded, failure is DailyOrchestrationStage.SNAPSHOT),
        RecordingFactsEngine(recorded, failure is DailyOrchestrationStage.IMPORTANT_FACTS),
        RecordingImpactEngine(recorded, failure is DailyOrchestrationStage.PORTFOLIO_IMPACT),
        RecordingPriorityEngine(recorded, failure is DailyOrchestrationStage.DAILY_PRIORITY),
        clock=lambda: NOW,
    )


def test_complete_real_flow_order_results_summary_and_separation() -> None:
    calls: list[str] = []
    result = orchestrator(calls).run(POSITIONS, (candidate(),), REFERENCE_DATE)

    assert calls == [stage.value for stage in DailyOrchestrationStage]
    assert result.status is DailyOrchestrationStatus.COMPLETED
    assert tuple(item.status for item in result.stages) == (DailyStageStatus.COMPLETED,) * 4
    assert result.reference_date == REFERENCE_DATE
    assert result.generated_at == NOW
    assert result.generated_at.utcoffset() == timedelta(0)
    assert result.snapshot is not None
    assert result.important_facts is not None
    assert result.portfolio_impacts is not None
    assert result.daily_priorities is not None
    assert result.summary.fact_count == 1
    assert result.summary.impact_count == 1
    assert result.summary.priority_count == 1
    assert result.summary.high_priority_count == 1
    assert result.summary.moderate_priority_count == 0
    assert result.summary.low_priority_count == 0
    assert result.summary.analyze_count == 0
    assert result.summary.decide_count == 1
    assert result.snapshot.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert result.snapshot.institutions == ("Bradesco", "Santander", "UBS")
    assert result.snapshot.currencies == ("BRL", "USD")
    assert result.snapshot.consolidated.gross_value_by_currency == {
        "BRL": Decimal("41.00"),
        "USD": Decimal("20.50"),
    }


@pytest.mark.parametrize("items", [(), POSITIONS[:1], POSITIONS[1:2], POSITIONS[2:]])
def test_empty_and_individual_institution_flows_complete(
    items: tuple[PortfolioPosition, ...],
) -> None:
    result = orchestrator().run(items, (), REFERENCE_DATE)
    assert result.status is DailyOrchestrationStatus.COMPLETED
    assert result.summary.fact_count == result.summary.impact_count == 0
    assert result.summary.priority_count == 0
    assert result.summary.completed_stage_count == 4


@pytest.mark.parametrize("failed_stage", tuple(DailyOrchestrationStage))
def test_failure_is_typed_chained_safe_and_stops_later_stages(
    failed_stage: DailyOrchestrationStage,
) -> None:
    calls: list[str] = []
    with pytest.raises(DailyOrchestrationError) as captured:
        orchestrator(calls, failed_stage).run(POSITIONS, (candidate(),), REFERENCE_DATE)

    error = captured.value
    result = error.result
    failed_index = tuple(DailyOrchestrationStage).index(failed_stage)
    assert error.stage is failed_stage
    assert error.__cause__ is not None
    assert "sensitive" not in str(error)
    assert "Traceback" not in str(error)
    assert calls == [stage.value for stage in tuple(DailyOrchestrationStage)[: failed_index + 1]]
    assert result.status is DailyOrchestrationStatus.FAILED
    assert tuple(item.status for item in result.stages) == (
        (DailyStageStatus.COMPLETED,) * failed_index
        + (DailyStageStatus.FAILED,)
        + (DailyStageStatus.SKIPPED,) * (3 - failed_index)
    )
    assert result.summary.failed_stage_count == 1
    assert result.summary.completed_stage_count == failed_index
    assert result.summary.skipped_stage_count == 3 - failed_index


def test_determinism_idempotence_and_inputs_are_not_mutated() -> None:
    positions = list(reversed(POSITIONS))
    candidates = [candidate()]
    before_positions = tuple(positions)
    before_candidates = tuple(candidates)

    first = orchestrator().run(positions, candidates, REFERENCE_DATE)
    second = orchestrator().run(tuple(reversed(positions)), candidates, REFERENCE_DATE)

    assert first == second
    assert tuple(positions) == before_positions
    assert tuple(candidates) == before_candidates
    assert len(first.daily_priorities.priorities if first.daily_priorities else ()) <= 3


def test_stage_execution_validates_time_and_error_contracts() -> None:
    normalized = DailyStageExecution(
        DailyOrchestrationStage.SNAPSHOT,
        DailyStageStatus.COMPLETED,
        NOW.astimezone(timezone(timedelta(hours=-3))),
        NOW,
    )
    assert normalized.started_at == NOW
    with pytest.raises(ValueError, match="earlier"):
        DailyStageExecution(
            DailyOrchestrationStage.SNAPSHOT,
            DailyStageStatus.COMPLETED,
            NOW,
            NOW - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="FAILED"):
        DailyStageExecution(
            DailyOrchestrationStage.SNAPSHOT,
            DailyStageStatus.FAILED,
            NOW,
            NOW,
        )
    with pytest.raises(ValueError, match="only a FAILED"):
        DailyStageExecution(
            DailyOrchestrationStage.SNAPSHOT,
            DailyStageStatus.SKIPPED,
            NOW,
            NOW,
            "Error",
            "invented",
        )
    with pytest.raises(ValueError, match="timezone"):
        DailyStageExecution(
            DailyOrchestrationStage.SNAPSHOT,
            DailyStageStatus.COMPLETED,
            datetime(2026, 7, 30),
            NOW,
        )


def test_new_contracts_are_frozen_and_summary_validates_counts() -> None:
    stage = DailyStageExecution(
        DailyOrchestrationStage.SNAPSHOT, DailyStageStatus.COMPLETED, NOW, NOW
    )
    with pytest.raises(FrozenInstanceError):
        setattr(stage, "status", DailyStageStatus.FAILED)
    with pytest.raises(ValueError, match="stage status"):
        DailyOrchestrationSummary(4, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_runtime_input_and_dependency_output_types_are_rejected() -> None:
    with pytest.raises(TypeError, match="PortfolioPosition"):
        orchestrator().run(cast(tuple[PortfolioPosition, ...], ("bad",)), (), REFERENCE_DATE)


def test_clock_must_be_aware() -> None:
    service = DailyOrchestrator(
        RecordingSnapshotBuilder([]),
        RecordingFactsEngine([]),
        RecordingImpactEngine([]),
        RecordingPriorityEngine([]),
        clock=lambda: datetime(2026, 7, 30),
    )
    with pytest.raises(ValueError, match="timezone"):
        service.run((), (), REFERENCE_DATE)
