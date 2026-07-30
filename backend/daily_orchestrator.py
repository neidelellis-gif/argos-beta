"""Deterministic orchestration of the official ARGOS daily engines."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Protocol

from backend.daily_portfolio_snapshot import (
    DailyPortfolioSnapshot,
    ValidationReportKey,
)
from backend.daily_priority import DailyPriorityResult
from backend.import_validation import ImportValidationReport
from backend.important_facts import FactCandidate, ImportantFactsResult
from backend.models import PortfolioPosition
from backend.portfolio_impact import PortfolioImpactResult


class DailyOrchestrationStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DailyOrchestrationStage(str, Enum):
    SNAPSHOT = "SNAPSHOT"
    IMPORTANT_FACTS = "IMPORTANT_FACTS"
    PORTFOLIO_IMPACT = "PORTFOLIO_IMPACT"
    DAILY_PRIORITY = "DAILY_PRIORITY"


class DailyStageStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


_STAGE_ORDER = tuple(DailyOrchestrationStage)


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class DailyStageExecution:
    stage: DailyOrchestrationStage
    status: DailyStageStatus
    started_at: datetime
    completed_at: datetime
    error_type: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stage, DailyOrchestrationStage):
            raise TypeError("stage must be a DailyOrchestrationStage")
        if not isinstance(self.status, DailyStageStatus):
            raise TypeError("status must be a DailyStageStatus")
        started = _aware_utc(self.started_at, "started_at")
        completed = _aware_utc(self.completed_at, "completed_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)
        if completed < started:
            raise ValueError("completed_at must not be earlier than started_at")
        has_error = bool(self.error_type and self.error_type.strip()) and bool(
            self.error_message and self.error_message.strip()
        )
        if self.status is DailyStageStatus.FAILED and not has_error:
            raise ValueError("FAILED stage must include error_type and error_message")
        if self.status is not DailyStageStatus.FAILED and (
            self.error_type is not None or self.error_message is not None
        ):
            raise ValueError("only a FAILED stage may include error information")


@dataclass(frozen=True)
class DailyOrchestrationSummary:
    stage_count: int
    completed_stage_count: int
    failed_stage_count: int
    skipped_stage_count: int
    fact_count: int
    impact_count: int
    priority_count: int
    high_priority_count: int
    moderate_priority_count: int
    low_priority_count: int
    analyze_count: int
    decide_count: int

    def __post_init__(self) -> None:
        counts = tuple(self.__dict__.values())
        if any(not isinstance(value, int) for value in counts):
            raise TypeError("summary counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("summary counts must not be negative")
        if self.stage_count != len(_STAGE_ORDER):
            raise ValueError("stage_count must match the official stage count")
        if self.completed_stage_count + self.failed_stage_count + self.skipped_stage_count != self.stage_count:
            raise ValueError("stage status counts must equal stage_count")
        if self.failed_stage_count > 1:
            raise ValueError("failed_stage_count must not exceed one")
        if self.priority_count > 3:
            raise ValueError("priority_count must not exceed three")
        if self.high_priority_count + self.moderate_priority_count + self.low_priority_count != self.priority_count:
            raise ValueError("priority level counts must equal priority_count")
        if self.analyze_count + self.decide_count != self.priority_count:
            raise ValueError("action counts must equal priority_count")


@dataclass(frozen=True)
class DailyOrchestrationResult:
    reference_date: date | None
    generated_at: datetime
    status: DailyOrchestrationStatus
    stages: tuple[DailyStageExecution, ...]
    snapshot: DailyPortfolioSnapshot | None
    important_facts: ImportantFactsResult | None
    portfolio_impacts: PortfolioImpactResult | None
    daily_priorities: DailyPriorityResult | None
    summary: DailyOrchestrationSummary

    def __post_init__(self) -> None:
        if self.reference_date is not None and not isinstance(self.reference_date, date):
            raise TypeError("reference_date must be a date or None")
        generated = _aware_utc(self.generated_at, "generated_at")
        object.__setattr__(self, "generated_at", generated)
        if not isinstance(self.status, DailyOrchestrationStatus):
            raise TypeError("status must be a DailyOrchestrationStatus")
        if not isinstance(self.stages, tuple):
            raise TypeError("stages must be a tuple")
        if tuple(item.stage for item in self.stages) != _STAGE_ORDER:
            raise ValueError("stages must follow the official order")
        if any(not isinstance(item, DailyStageExecution) for item in self.stages):
            raise TypeError("stages accepts only DailyStageExecution instances")
        statuses = tuple(item.status for item in self.stages)
        if DailyStageStatus.PENDING in statuses:
            raise ValueError("final stages must not be PENDING")
        expected_counts = (
            statuses.count(DailyStageStatus.COMPLETED),
            statuses.count(DailyStageStatus.FAILED),
            statuses.count(DailyStageStatus.SKIPPED),
        )
        if expected_counts != (
            self.summary.completed_stage_count,
            self.summary.failed_stage_count,
            self.summary.skipped_stage_count,
        ):
            raise ValueError("summary does not match stage statuses")
        if self.status is DailyOrchestrationStatus.COMPLETED:
            if any(item is None for item in (self.snapshot, self.important_facts, self.portfolio_impacts, self.daily_priorities)):
                raise ValueError("COMPLETED result must include every stage result")
            if any(status is not DailyStageStatus.COMPLETED for status in statuses):
                raise ValueError("COMPLETED result requires all stages completed")
        else:
            if expected_counts[1] != 1:
                raise ValueError("FAILED result requires exactly one failed stage")
            failed_index = statuses.index(DailyStageStatus.FAILED)
            if statuses[:failed_index] != (DailyStageStatus.COMPLETED,) * failed_index:
                raise ValueError("stages before failure must be COMPLETED")
            if statuses[failed_index + 1 :] != (DailyStageStatus.SKIPPED,) * (len(statuses) - failed_index - 1):
                raise ValueError("stages after failure must be SKIPPED")


class DailyOrchestrationError(Exception):
    """A failed orchestration with a safe, immutable partial result."""

    def __init__(
        self,
        stage: DailyOrchestrationStage,
        error_type: str,
        result: DailyOrchestrationResult,
    ) -> None:
        self.stage = stage
        self.error_type = error_type
        self.result = result
        super().__init__(f"Daily orchestration failed at {stage.value}: {error_type}.")


class _SnapshotBuilder(Protocol):
    def build(
        self,
        positions: Iterable[PortfolioPosition],
        reference_date: date | None = None,
        validation_reports: Mapping[ValidationReportKey, ImportValidationReport] | None = None,
    ) -> DailyPortfolioSnapshot: ...


class _ImportantFactsEngine(Protocol):
    def select(
        self, candidates: Iterable[FactCandidate], snapshot: DailyPortfolioSnapshot
    ) -> ImportantFactsResult: ...


class _PortfolioImpactEngine(Protocol):
    def build(
        self, snapshot: DailyPortfolioSnapshot, facts_result: ImportantFactsResult
    ) -> PortfolioImpactResult: ...


class _DailyPriorityEngine(Protocol):
    def build(
        self,
        snapshot: DailyPortfolioSnapshot,
        facts_result: ImportantFactsResult,
        impact_result: PortfolioImpactResult,
    ) -> DailyPriorityResult: ...


class DailyOrchestrator:
    """Coordinate the four daily engines without reproducing their decisions."""

    def __init__(
        self,
        snapshot_builder: _SnapshotBuilder,
        important_facts_engine: _ImportantFactsEngine,
        portfolio_impact_engine: _PortfolioImpactEngine,
        daily_priority_engine: _DailyPriorityEngine,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._snapshot_builder = snapshot_builder
        self._important_facts_engine = important_facts_engine
        self._portfolio_impact_engine = portfolio_impact_engine
        self._daily_priority_engine = daily_priority_engine
        self._clock = clock

    def run(
        self,
        positions: Iterable[PortfolioPosition],
        fact_candidates: Iterable[FactCandidate],
        reference_date: date | None = None,
        validation_reports: Mapping[ValidationReportKey, ImportValidationReport] | None = None,
    ) -> DailyOrchestrationResult:
        position_items = tuple(positions)
        candidate_items = tuple(fact_candidates)
        if any(not isinstance(item, PortfolioPosition) for item in position_items):
            raise TypeError("positions accepts only PortfolioPosition instances")
        if any(not isinstance(item, FactCandidate) for item in candidate_items):
            raise TypeError("fact_candidates accepts only FactCandidate instances")
        if reference_date is not None and not isinstance(reference_date, date):
            raise TypeError("reference_date must be a date or None")

        stages: list[DailyStageExecution] = []
        snapshot: DailyPortfolioSnapshot | None = None
        facts: ImportantFactsResult | None = None
        impacts: PortfolioImpactResult | None = None
        priorities: DailyPriorityResult | None = None

        for stage in _STAGE_ORDER:
            started = self._now()
            try:
                if stage is DailyOrchestrationStage.SNAPSHOT:
                    value = self._snapshot_builder.build(position_items, reference_date, validation_reports)
                    if not isinstance(value, DailyPortfolioSnapshot):
                        raise TypeError("snapshot builder must return DailyPortfolioSnapshot")
                    _aware_utc(value.generated_at, "snapshot generated_at")
                    snapshot = value
                elif stage is DailyOrchestrationStage.IMPORTANT_FACTS:
                    if snapshot is None:
                        raise RuntimeError("snapshot is unavailable")
                    value_facts = self._important_facts_engine.select(candidate_items, snapshot)
                    if not isinstance(value_facts, ImportantFactsResult):
                        raise TypeError("important facts engine must return ImportantFactsResult")
                    facts = value_facts
                elif stage is DailyOrchestrationStage.PORTFOLIO_IMPACT:
                    if snapshot is None or facts is None:
                        raise RuntimeError("required prior result is unavailable")
                    value_impacts = self._portfolio_impact_engine.build(snapshot, facts)
                    if not isinstance(value_impacts, PortfolioImpactResult):
                        raise TypeError("portfolio impact engine must return PortfolioImpactResult")
                    _aware_utc(value_impacts.generated_at, "portfolio impact generated_at")
                    if value_impacts.reference_date != snapshot.reference_date:
                        raise ValueError("portfolio impact reference_date must match snapshot")
                    impacts = value_impacts
                else:
                    if snapshot is None or facts is None or impacts is None:
                        raise RuntimeError("required prior result is unavailable")
                    value_priorities = self._daily_priority_engine.build(snapshot, facts, impacts)
                    if not isinstance(value_priorities, DailyPriorityResult):
                        raise TypeError("daily priority engine must return DailyPriorityResult")
                    _aware_utc(value_priorities.generated_at, "daily priority generated_at")
                    if value_priorities.reference_date != snapshot.reference_date:
                        raise ValueError("daily priority reference_date must match snapshot")
                    priorities = value_priorities
                completed = self._now_not_before(started)
                stages.append(DailyStageExecution(stage, DailyStageStatus.COMPLETED, started, completed))
            except Exception as cause:
                completed = self._now_not_before(started)
                error_type = type(cause).__name__
                message = f"Daily orchestration failed at {stage.value}: {error_type}."
                stages.append(DailyStageExecution(stage, DailyStageStatus.FAILED, started, completed, error_type, message))
                stages.extend(
                    DailyStageExecution(later, DailyStageStatus.SKIPPED, completed, completed)
                    for later in _STAGE_ORDER[len(stages) :]
                )
                result = self._result(
                    DailyOrchestrationStatus.FAILED, tuple(stages), snapshot, facts,
                    impacts, priorities, self._now_not_before(completed),
                )
                raise DailyOrchestrationError(stage, error_type, result) from cause

        return self._result(
            DailyOrchestrationStatus.COMPLETED, tuple(stages), snapshot, facts,
            impacts, priorities, self._now_not_before(stages[-1].completed_at),
        )

    def _now(self) -> datetime:
        return _aware_utc(self._clock(), "orchestrator clock")

    def _now_not_before(self, earlier: datetime) -> datetime:
        value = self._now()
        if value < earlier:
            raise ValueError("orchestrator clock must not move backwards")
        return value

    @staticmethod
    def _result(
        status: DailyOrchestrationStatus,
        stages: tuple[DailyStageExecution, ...],
        snapshot: DailyPortfolioSnapshot | None,
        facts: ImportantFactsResult | None,
        impacts: PortfolioImpactResult | None,
        priorities: DailyPriorityResult | None,
        generated_at: datetime,
    ) -> DailyOrchestrationResult:
        priority_summary = priorities.summary if priorities is not None else None
        summary = DailyOrchestrationSummary(
            stage_count=len(_STAGE_ORDER),
            completed_stage_count=sum(item.status is DailyStageStatus.COMPLETED for item in stages),
            failed_stage_count=sum(item.status is DailyStageStatus.FAILED for item in stages),
            skipped_stage_count=sum(item.status is DailyStageStatus.SKIPPED for item in stages),
            fact_count=len(facts.important_facts) if facts is not None else 0,
            impact_count=len(impacts.impacts) if impacts is not None else 0,
            priority_count=priority_summary.selected_priority_count if priority_summary else 0,
            high_priority_count=priority_summary.high_priority_count if priority_summary else 0,
            moderate_priority_count=priority_summary.moderate_priority_count if priority_summary else 0,
            low_priority_count=priority_summary.low_priority_count if priority_summary else 0,
            analyze_count=priority_summary.analyze_count if priority_summary else 0,
            decide_count=priority_summary.decide_count if priority_summary else 0,
        )
        return DailyOrchestrationResult(
            reference_date=snapshot.reference_date if snapshot is not None else None,
            generated_at=generated_at,
            status=status,
            stages=stages,
            snapshot=snapshot,
            important_facts=facts,
            portfolio_impacts=impacts,
            daily_priorities=priorities,
            summary=summary,
        )
